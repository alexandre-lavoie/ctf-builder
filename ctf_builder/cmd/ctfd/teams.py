import argparse
import dataclasses
import json
import os.path
import typing
import uuid

from ...ctfd import CTFdAPI, ctfd_errors
from ...error import LibError, get_exit_status, print_errors
from ..common import CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    file: str
    output: str
    url: str = dataclasses.field(default="http://localhost:8000")


@dataclasses.dataclass(frozen=True)
class Context:
    session: CTFdAPI


@dataclasses.dataclass
class User:
    name: str
    email: str
    id: int = dataclasses.field(default=-1)
    password: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    banned: bool = dataclasses.field(default=False)
    hidden: bool = dataclasses.field(default=False)
    type: str = dataclasses.field(default="user")
    verified: bool = dataclasses.field(default=True)

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "User":
        fields = {}

        for field in dataclasses.fields(cls):
            value = data.get(field.name)
            if value is None:
                continue

            fields[field.name] = field.type(value)

        return cls(**fields)

    def to_api(self) -> typing.Dict[str, typing.Any]:
        d = self.to_dict()

        del d["id"]

        return d

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        out = {}

        for field in dataclasses.fields(User):
            out[field.name] = getattr(self, field.name)

        return out


@dataclasses.dataclass
class Team:
    name: str
    email: str
    id: int = dataclasses.field(default=-1)
    password: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    banned: bool = dataclasses.field(default=False)
    hidden: bool = dataclasses.field(default=False)
    users: typing.Sequence[User] = dataclasses.field(default_factory=list)

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "Team":
        fields = {}

        for field in dataclasses.fields(cls):
            value = data.get(field.name)
            if value is None:
                continue

            fields[field.name] = value

        fields["users"] = [User.from_dict(user) for user in (data.get("users") or [])]

        return cls(**fields)

    def to_api(self) -> typing.Dict[str, typing.Any]:
        d = self.to_dict()

        del d["id"]
        del d["users"]

        return d

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        out = {}

        for field in dataclasses.fields(Team):
            out[field.name] = getattr(self, field.name)

        out["users"] = [user.to_dict() for user in self.users]

        return out


def make_teams(file: str) -> typing.List[Team]:
    with open(file, "r") as h:
        data = json.load(h)

    return [Team.from_dict(team) for team in data["teams"]]


def deploy_user(user: User, context: Context) -> typing.Sequence[LibError]:
    res = context.session.get("/users", data={"q": user.email})

    user_api = None
    if res.status_code == 200:
        data = res.json()["data"]

        if len(data) == 1:
            user_api = data[0]

    if user_api:
        res = context.session.patch(f"/users/{user_api['id']}", data=user.to_api())
    else:
        res = context.session.post(
            "/users",
            data=user.to_api(),
        )

    if res_errors := ctfd_errors(res, context=f"User {user.name}"):
        return res_errors

    data = res.json()["data"]
    user.id = data["id"]

    return []


def add_user_to_team(
    team_id: int, user_id: int, context: Context
) -> typing.Sequence[LibError]:
    res = context.session.get(f"/teams/{team_id}/members")

    if res.status_code == 200:
        user_ids = set(res.json()["data"])

        if user_id in user_ids:
            return []

    res = context.session.post(
        f"/teams/{team_id}/members",
        data={"user_id": user_id},
    )

    return ctfd_errors(res, context=f"User {user_id}")


def deploy_team(team: Team, context: Context) -> typing.Sequence[LibError]:
    res = context.session.get("/teams", data={"q": team.email})

    team_api = None
    if res.status_code == 200:
        data = res.json()["data"]

        if len(data) == 1:
            team_api = data[0]

    if team_api:
        res = context.session.patch(f"/teams/{team_api['id']}", data=team.to_api())
    else:
        res = context.session.post(
            "/teams",
            data=team.to_api(),
        )

    if res_errors := ctfd_errors(res, context="Team"):
        return res_errors

    data = res.json()["data"]
    team_id = data["id"]

    team.id = team_id

    errors: typing.List[LibError] = []
    for user in team.users:
        user_errors = deploy_user(user, context)
        if user_errors:
            errors += user_errors
            continue

        errors += add_user_to_team(team.id, user.id, context)

    return errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument("-k", "--api_key", help="API Key", required=True)
    parser.add_argument(
        "-u", "--url", help="URL for CTFd", default="http://localhost:8000"
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Config file path",
        default=os.path.join(root_directory, "ctfd", "teams.json"),
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file",
        default=os.path.join(root_directory, "ctfd", "teams.out.json"),
    )


def merge_teams_json(
    old: typing.Dict[str, typing.Any], new: typing.Dict[str, typing.Any]
) -> typing.Dict[str, typing.Any]:
    out = {**new}

    teams = []
    for old_team, new_team in zip(old["teams"], new["teams"]):
        team = {**new_team}

        team["password"] = old_team["password"]

        users = []
        for old_user, new_user in zip(old_team["users"], new_team["users"]):
            user = {**new_user}

            user["password"] = old_user["password"]

            users.append(user)

        team["users"] = users

        teams.append(team)

    out["teams"] = teams

    return out


def cli(args: Args, cli_context: CliContext) -> bool:
    teams = make_teams(args.file)

    context = Context(session=CTFdAPI(args.url, args.api_key))

    all_errors: typing.List[LibError] = []

    out_teams: typing.List[Team] = []
    for team in teams:
        errors = deploy_team(team, context)
        all_errors += errors

        print_errors(
            prefix=[team.name],
            errors=errors,
            console=cli_context.console,
        )

        if not errors:
            out_teams.append(team)

    out_json = {"teams": [team.to_dict() for team in out_teams]}

    if os.path.isfile(args.output):
        with open(args.output) as h:
            try:
                old_json = json.load(h)
                out_json = merge_teams_json(old_json, out_json)
            except ValueError:
                pass

    with open(args.output, "w") as h:
        json.dump(out_json, h, indent=2)

    return get_exit_status(all_errors)
