import io
import json
import os.path
import time
import typing

import docker
import docker.models.containers
import rich.console

from ctf_builder.cmd.build import Args as BuildArgs
from ctf_builder.cmd.build import cli as build_cli
from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.ctfd.challenges import Args as ChallengesArgs
from ctf_builder.cmd.ctfd.challenges import cli as challenges_cli
from ctf_builder.cmd.ctfd.setup import Args as SetupArgs
from ctf_builder.cmd.ctfd.setup import cli as setup_cli
from ctf_builder.cmd.ctfd.teams import Args as TeamsArgs
from ctf_builder.cmd.ctfd.teams import cli as teams_cli
from ctf_builder.config import CHALLENGE_BASE_PORT
from ctf_builder.ctfd import generate_key


TEST_NAME = "test"
TEST_PASSWORD = "test"
TEST_EMAIL = "test@ctf.com"
TEST_PORT = 9876
TEST_URL = f"http://localhost:{TEST_PORT}/"
TEST_CHALLENGES: typing.List[str] = []


def test() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    # Create a CTFd container
    container: docker.models.containers.Container = (
        context.docker_client.containers.run(
            image="ctfd/ctfd",
            ports={"8000": TEST_PORT},
            detach=True,
            remove=True,
            healthcheck={
                "test": "python -c \"import requests; requests.get('http://localhost:8000/')\" || exit 1",
                "interval": 1_000_000_000,
                "timeout": 1_000_000_000,
                "retries": 10,
                "start_period": 1_000_000_000,
            },
        )
    )

    try:
        # Wait for container to be healthy
        for _ in range(40):
            container.reload()

            if container.health == "healthy":
                break

            time.sleep(0.5)
        else:
            assert False, "Container failed to start"

        # Setup CTFd
        assert setup_cli(
            cli_context=context,
            args=SetupArgs(
                name=TEST_NAME,
                email=TEST_EMAIL,
                password=TEST_PASSWORD,
                file=os.path.join(context.root_directory, "ctfd", "setup.json"),
                url=TEST_URL,
            ),
        )

        # Generate a token for admin account
        token = generate_key(TEST_URL, name=TEST_NAME, password=TEST_PASSWORD)
        assert token, "Failed to generate api key"

        api_key = token[1]

        # Deploy teams
        teams_output = io.StringIO()
        assert teams_cli(
            cli_context=context,
            args=TeamsArgs(
                api_key=api_key,
                file=os.path.join(context.root_directory, "ctfd", "teams.json"),
                output=teams_output,
                url=TEST_URL,
            ),
        )
        teams_output.seek(0)

        assert json.load(teams_output)

        # Build challenges
        assert build_cli(cli_context=context, args=BuildArgs(challenge=TEST_CHALLENGES))

        # Deploy challenges
        assert challenges_cli(
            cli_context=context,
            args=ChallengesArgs(
                api_key=api_key,
                url=TEST_URL,
                port=CHALLENGE_BASE_PORT,
                challenge=TEST_CHALLENGES,
            ),
        )
    finally:
        container.remove(force=True)
