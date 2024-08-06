import os.path
import typing

import docker
import rich.console

from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.test import Args, cli


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

    assert cli(cli_context=context, args=Args(challenge=TEST_CHALLENGES))
