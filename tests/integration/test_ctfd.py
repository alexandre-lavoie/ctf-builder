import json
import os.path
import tempfile
import typing

import docker
import docker.models.containers
import rich.console

from ctf_builder.cmd.build import Args as BuildArgs
from ctf_builder.cmd.build import cli as build_cli
from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.ctfd.challenges import Args as ChallengesArgs
from ctf_builder.cmd.ctfd.challenges import cli as challenges_cli
from ctf_builder.cmd.ctfd.dev import Args as DevArgs
from ctf_builder.cmd.ctfd.dev import cli as dev_cli
from ctf_builder.cmd.ctfd.setup import Args as SetupArgs
from ctf_builder.cmd.ctfd.setup import cli as setup_cli
from ctf_builder.cmd.ctfd.teams import Args as TeamsArgs
from ctf_builder.cmd.ctfd.teams import cli as teams_cli
from ctf_builder.config import CHALLENGE_BASE_PORT, CHALLENGE_HOST
from ctf_builder.ctfd.api import CTFdAPI
from ctf_builder.ctfd.docker import ctfd_container


TEST_NAME = "test"
TEST_PASSWORD = "test"
TEST_EMAIL = "test@ctf.com"
TEST_HOST = CHALLENGE_HOST
TEST_CHALLENGE_HOST = "challenges"
TEST_PORT = 9876
TEST_URL = f"http://{TEST_HOST}:{TEST_PORT}/"
TEST_CHALLENGES: typing.List[str] = []


def test_ctfd_dev() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    assert dev_cli(cli_context=context, args=DevArgs(port=TEST_PORT, exit=True))


def test_ctfd_deploy() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    container, _ = ctfd_container(docker_client=context.docker_client, port=TEST_PORT)
    assert container, "Container did not start"

    try:
        # Setup CTFd
        assert setup_cli(
            cli_context=context,
            args=SetupArgs(
                name=TEST_NAME,
                email=TEST_EMAIL,
                password=TEST_PASSWORD,
                file=os.path.join(context.root_directory, "ctfd", "setup.json"),
                url=TEST_URL,
                skip_ssl=True,
            ),
        )

        # Connect to API
        api = CTFdAPI.login(
            TEST_URL, name=TEST_NAME, password=TEST_PASSWORD, verify_ssl=False
        )
        assert api, "Failed to generate api key"

        # Deploy teams
        with tempfile.TemporaryDirectory() as temp_dir:
            output = os.path.join(temp_dir, "teams.json")
            team_args = TeamsArgs(
                api_key=api.session.access_token.value or "",
                file=os.path.join(context.root_directory, "ctfd", "teams.json"),
                output=output,
                url=TEST_URL,
                skip_ssl=True,
            )

            # First deploy
            assert teams_cli(
                cli_context=context,
                args=team_args,
            )

            with open(output) as h:
                old_teams = json.load(h)

            # Second deploy, should sync
            assert teams_cli(
                cli_context=context,
                args=team_args,
            )

            with open(output) as h:
                new_teams = json.load(h)

            assert old_teams == new_teams, "Teams do not match"

        # Build challenges
        assert build_cli(cli_context=context, args=BuildArgs(challenge=TEST_CHALLENGES))

        # Deploy challenges
        challenge_args = ChallengesArgs(
            api_key=api.session.access_token.value or "",
            url=TEST_URL,
            host=TEST_CHALLENGE_HOST,
            port=CHALLENGE_BASE_PORT,
            challenge=TEST_CHALLENGES,
            skip_ssl=True,
        )

        ## First Deploy
        assert challenges_cli(
            cli_context=context,
            args=challenge_args,
        )

        ## Second Deploy
        assert challenges_cli(
            cli_context=context,
            args=challenge_args,
        )
    finally:
        container.remove(force=True)
