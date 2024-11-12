import argparse
import dataclasses
import json
import os.path
import typing
import uuid

import pydantic_core

from ...ctfd.api import CTFdAPI
from ...ctfd.models import CTFdAccessToken, CTFdTeam, CTFdUser
from ...ctfd.session import CTFdSession
from ...error import (
    DeployError,
    LibError,
    disable_ssl_warnings,
    get_exit_status,
    print_errors,
)
from ...models.team import TeamFile
from ..common import CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    file: str
    output: str
    url: str = dataclasses.field(default="http://localhost:8000")
    skip_ssl: bool = dataclasses.field(default=False)


@dataclasses.dataclass(frozen=True)
class Context:
    api: CTFdAPI


def deploy_user(user: CTFdUser, context: Context) -> typing.Sequence[LibError]:
    data, _ = context.api.get_users_by_query(user.name or "")

    res_errors: typing.Sequence[LibError]
    if data and any(ctfd_user.name == user.name for ctfd_user in data):
        for ctfd_user in data:
            if ctfd_user.name == user.name:
                break

        user.id = ctfd_user.id

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


def deploy_team(
    team: CTFdTeam, users: typing.Sequence[CTFdUser], context: Context
) -> typing.Sequence[LibError]:
    try:
        data, _ = context.api.get_teams_by_query(team.name or "")

        solo = False
    except pydantic_core.ValidationError:
        solo = True

    if not solo:
        res_errors: typing.Sequence[LibError]

        if data and any(ctfd_team.name == team.name for ctfd_team in data):
            for ctfd_team in data:
                if ctfd_team.name == team.name:
                    break

            team.id = ctfd_team.id

            res, res_errors = context.api.update_team(team)
        else:
            if not team.password:
                team.password = str(uuid.uuid4())

            res, res_errors = context.api.create_team(team)

        if res is None:
            return res_errors

        team.id = res.id
    else:
        team.id = 0

    errors: typing.List[LibError] = []
    for user in users:
        user_errors = deploy_user(user, context)
        if user_errors:
            errors += user_errors
            continue

        if not solo:
            errors += add_user_to_team(team.id, user.id, context)

    return errors


def merge_teams_json(
    old: typing.Dict[str, typing.Any], new: typing.Dict[str, typing.Any]
) -> typing.Dict[str, typing.Any]:
    out = {**new}

    old_teams = {team["email"]: team for team in old["teams"]}

    teams = []
    for new_team in new["teams"]:
        team = {**new_team}

        old_team = old_teams.get(new_team["email"])
        if old_team is None:
            teams.append(team)
            continue

        if password := old_team.get("password"):
            team["password"] = password

        old_users = {user["email"]: user for user in old_team["users"]}

        users = []
        for new_user in new_team["users"]:
            user = {**new_user}

            old_user = old_users.get(new_user["email"])
            if old_user and (password := old_user.get("password")):
                user["password"] = password

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
    parser.add_argument(
        "-s",
        "--skip_ssl",
        action="store_true",
        help="Skip SSL check",
        default=False,
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    if args.skip_ssl:
        disable_ssl_warnings()

    with open(args.file, "r") as h:
        config = json.load(h)

    team_file = TeamFile(**config)

    context = Context(
        CTFdAPI(
            CTFdSession(
                url=args.url,
                access_token=CTFdAccessToken(id=-1, value=args.api_key),
                verify_ssl=not args.skip_ssl,
            )
        )
    )

    all_errors: typing.List[LibError] = []

    teams: typing.List[typing.Dict[str, typing.Any]] = []
    for team in team_file.teams:
        ctfd_team = CTFdTeam(id=-1, name=team.name, email=team.email)

        ctfd_users = [
            CTFdUser(id=-1, name=user.name, email=user.email) for user in team.users
        ]

        errors = deploy_team(team=ctfd_team, users=ctfd_users, context=context)
        all_errors += errors

        print_errors(
            prefix=[team.name or "team"],
            errors=errors,
            console=cli_context.console,
        )

        if not errors:
            teams.append(
                {
                    **ctfd_team.model_dump(mode="json"),
                    "users": [user.model_dump(mode="json") for user in ctfd_users],
                }
            )

    out_json = {"teams": teams}

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
