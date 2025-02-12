import os.path
import tempfile
import typing

import docker
import rich.console

from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.docker.list import Args, cli


TEST_CHALLENGES: typing.List[str] = []
EXPECTED_INSTANCES: typing.List[str] = ["deploy-0", "multi-deploy-0", "multi-deploy-1"]


def test() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = os.path.join(temp_dir, "output")

        assert cli(
            cli_context=context,
            args=Args(challenge=TEST_CHALLENGES, output=output_path),
        )

        with open(output_path) as h:
            output = h.read()

    lines = output.split("\n")

    for v in EXPECTED_INSTANCES:
        assert v in lines, f"{v} not found"
