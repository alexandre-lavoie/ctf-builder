import argparse
import dataclasses
import json
import os.path
import typing
import uuid

from ...ctfd import CTFdAPI
from ...error import DeployError, LibError, get_exit_status, print_errors
from ..common import CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    file: str
    output: typing.Union[str, typing.TextIO]
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
    res = context.session.post(
        "/users",
        user.to_api(),
    )

    if res.status_code != 200:
        return [
            DeployError(
                context=f"User {user.name}",
                msg="failed to deploy",
                error=ValueError(res.json()["message"]),
            )
        ]

    data = res.json()["data"]
    user.id = data["id"]

    return []


def add_user_to_team(
    team_id: int, user_id: int, context: Context
) -> typing.Sequence[LibError]:
    res = context.session.post(
        f"/teams/{team_id}/members",
        {"user_id": user_id},
    )

    if res.status_code != 200:
        return [
            DeployError(
                context=f"User {user_id}",
                msg="failed to deploy",
                error=ValueError(res.json()["message"]),
            )
        ]

    return []


def deploy_team(team: Team, context: Context) -> typing.Sequence[LibError]:
    res = context.session.post(
        "/teams",
        team.to_api(),
    )

    if res.status_code != 200:
        return [
            DeployError(
                context="Team",
                msg="failed to deploy",
                error=ValueError(res.json()["message"]),
            )
        ]

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

    if cli_context.console:
        cli_context.console.print()

    out_json = [team.to_dict() for team in out_teams]
    if isinstance(args.output, str):
        with open(args.output, "w") as h:
            json.dump(out_json, h, indent=2)
    else:
        json.dump(out_json, args.output, indent=2)

    return get_exit_status(all_errors)
