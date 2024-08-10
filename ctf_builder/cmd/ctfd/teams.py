import argparse
import dataclasses
import json
import os.path
import typing
import uuid

from ...ctfd.api import CTFdAPI
from ...ctfd.models import CTFdAccessToken, CTFdTeam, CTFdUser
from ...ctfd.session import CTFdSession
from ...error import DeployError, LibError, get_exit_status, print_errors
from ..common import CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    file: str
    output: str
    url: str = dataclasses.field(default="http://localhost:8000")


@dataclasses.dataclass(frozen=True)
class Context:
    api: CTFdAPI


@dataclasses.dataclass
class TeamFile:
    team: CTFdTeam
    users: typing.List[CTFdUser]


def make_teams(file: str) -> typing.List[TeamFile]:
    with open(file, "r") as h:
        data = json.load(h)

    teams = []
    for team in data["teams"]:
        team["id"] = -1
        ctfd_team = CTFdTeam(**team)

        users = []
        for user in team["users"]:
            user["id"] = -1
            ctfd_user = CTFdUser(**user)

            users.append(ctfd_user)

        teams.append(TeamFile(team=ctfd_team, users=users))

    return teams


def deploy_user(user: CTFdUser, context: Context) -> typing.Sequence[LibError]:
    data, _ = context.api.get_users_by_query(user.email or "")

    res_errors: typing.Sequence[LibError]
    if data:
        user.id = data[0].id

        res, res_errors = context.api.update_user(user)
    else:
        if not user.password:
            user.password = str(uuid.uuid4())

        res, res_errors = context.api.create_user(user)

    if res is None:
        return res_errors

    user.id = res.id

    return []


def add_user_to_team(
    team_id: int, user_id: int, context: Context
) -> typing.Sequence[LibError]:
    user_ids, _ = context.api.get_users_in_team(team_id)

    if user_ids and user_id in user_ids:
        return []

    is_ok = context.api.add_user_to_team(team_id, user_id)

    return (
        []
        if is_ok
        else [
            DeployError(
                context=f"User {user_id}", msg=f"failed to add to team {team_id}"
            )
        ]
    )


def deploy_team(team_file: TeamFile, context: Context) -> typing.Sequence[LibError]:
    data, _ = context.api.get_teams_by_query(team_file.team.email or "")

    res_errors: typing.Sequence[LibError]
    if data:
        team_file.team.id = data[0].id

        res, res_errors = context.api.update_team(team_file.team)
    else:
        if not team_file.team.password:
            team_file.team.password = str(uuid.uuid4())

        res, res_errors = context.api.create_team(team_file.team)

    if res is None:
        return res_errors

    team_file.team.id = res.id

    errors: typing.List[LibError] = []
    for user in team_file.users:
        user_errors = deploy_user(user, context)
        if user_errors:
            errors += user_errors
            continue

        errors += add_user_to_team(team_file.team.id, user.id, context)

    return errors


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

    context = Context(
        CTFdAPI(
            CTFdSession(
                url=args.url, access_token=CTFdAccessToken(id=-1, value=args.api_key)
            )
        )
    )

    all_errors: typing.List[LibError] = []

    out_teams: typing.List[TeamFile] = []
    for team_file in teams:
        errors = deploy_team(team_file, context)
        all_errors += errors

        print_errors(
            prefix=[team_file.team.name or "team"],
            errors=errors,
            console=cli_context.console,
        )

        if not errors:
            out_teams.append(team_file)

    out_json = {
        "teams": [
            {
                **team_file.team.model_dump(mode="json"),
                "users": [user.model_dump(mode="json") for user in team_file.users],
            }
            for team_file in out_teams
        ]
    }

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
