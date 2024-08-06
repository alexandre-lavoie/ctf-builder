import argparse
import dataclasses
import json
import os.path
import typing
import uuid

import requests

from ..common import CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    url: str
    file: str
    output: str


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
    def from_dict(cls, data: typing.Dict) -> "User":
        fields = {}

        for field in dataclasses.fields(cls):
            value = data.get(field.name)
            if value is None:
                continue

            fields[field.name] = field.type(value)

        return cls(**fields)

    def to_api(self) -> typing.Dict:
        d = self.to_dict()

        del d["id"]

        return d

    def to_dict(self) -> typing.Dict:
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
    def from_dict(cls, data: typing.Dict) -> "Team":
        fields = {}

        for field in dataclasses.fields(cls):
            value = data.get(field.name)
            if value is None:
                continue

            fields[field.name] = value

        fields["users"] = [User.from_dict(user) for user in (data.get("users") or [])]

        return cls(**fields)

    def to_api(self) -> typing.Dict:
        d = self.to_dict()

        del d["id"]
        del d["users"]

        return d

    def to_dict(self) -> typing.Dict:
        out = {}

        for field in dataclasses.fields(Team):
            out[field.name] = getattr(self, field.name)

        out["users"] = [user.to_dict() for user in self.users]

        return out


def make_teams(file: str) -> typing.List[Team]:
    with open(file, "r") as h:
        data = json.load(h)

    return [Team.from_dict(team) for team in data["teams"]]


def build_user(url: str, api_key: str, user: User) -> bool:
    res = requests.post(
        f"{url}/api/v1/users",
        headers={"Authorization": f"Token {api_key}"},
        json=user.to_api(),
    )

    if res.status_code != 200:
        return False

    data = res.json()["data"]
    user.id = data["id"]

    return True


def add_user_to_team(url: str, api_key: str, team_id: int, user_id: int) -> bool:
    res = requests.post(
        f"{url}/api/v1/teams/{team_id}/members",
        headers={"Authorization": f"Token {api_key}"},
        json={"user_id": user_id},
    )

    return res.status_code == 200


def build_team(url: str, api_key: str, team: Team) -> bool:
    res = requests.post(
        f"{url}/api/v1/teams",
        headers={"Authorization": f"Token {api_key}"},
        json=team.to_api(),
    )

    if res.status_code == 200:
        data = res.json()["data"]
        team_id = data["id"]
    else:
        return False

    team.id = team_id

    for user in team.users:
        if build_user(url, api_key, user):
            add_user_to_team(url, api_key, team.id, user.id)

    return True


def cli_args(parser: argparse.ArgumentParser, root_directory: str):
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

    out: typing.List[Team] = []
    for team in teams:
        if build_team(args.url, args.api_key, team):
            out.append(team)

    with open(args.output, "w") as h:
        json.dump([team.to_dict() for team in out], h, indent=2)

    return True
