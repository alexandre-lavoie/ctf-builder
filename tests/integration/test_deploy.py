import os.path
import typing
import uuid

import docker
import rich.console

from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.docker.deploy import Args as DeployArgs
from ctf_builder.cmd.docker.deploy import cli as deploy_cli
from ctf_builder.cmd.docker.start import Args as StartArgs
from ctf_builder.cmd.docker.start import cli as start_cli
from ctf_builder.cmd.docker.stop import Args as StopArgs
from ctf_builder.cmd.docker.stop import cli as stop_cli
from ctf_builder.config import CHALLENGE_BASE_PORT


TEST_CHALLENGES: typing.List[str] = []


def test_deploy() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    assert deploy_cli(
        cli_context=context,
        args=DeployArgs(challenge=TEST_CHALLENGES, repository="repo"),
    )


def test_start_stop() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    network = str(f"ctf-builder_test-{uuid.uuid4()}")

    try:
        assert start_cli(
            cli_context=context,
            args=StartArgs(
                challenge=TEST_CHALLENGES,
                ip=[None],
                network=[network],
                port=CHALLENGE_BASE_PORT,
                detach=True,
            ),
        )
    finally:
        try:
            assert stop_cli(
                cli_context=context,
                args=StopArgs(challenge=TEST_CHALLENGES, network=[network]),
            )
        finally:
            try:
                context.docker_client.api.remove_network(network)
            except:
                pass
