import os.path
import uuid

import docker

import rich.console

from ctf_builder.config import CHALLENGE_BASE_PORT
from ctf_builder.cmd.common import CliContext

from ctf_builder.cmd.start import cli as start_cli, Args as StartArgs
from ctf_builder.cmd.stop import cli as stop_cli, Args as StopArgs


def test():
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    network = str(f"ctf-builder_test_{uuid.uuid4()}")

    try:
        assert start_cli(
            cli_context=context,
            args=StartArgs(
                challenge=[],
                ip=[None],
                network=[network],
                port=CHALLENGE_BASE_PORT,
                detach=True,
            ),
        )
    finally:
        assert stop_cli(
            cli_context=context, args=StopArgs(challenge=[], network=[network])
        )
