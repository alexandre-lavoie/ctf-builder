import json
import os.path
import tempfile

import docker
import rich.console

from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.documentation import Args, cli


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
        assert cli(cli_context=context, args=Args(output=temp_dir))

        with open(os.path.join(temp_dir, "challenge.json")) as h:
            assert json.load(h)

        with open(os.path.join(temp_dir, "teams.json")) as h:
            assert json.load(h)

        with open(os.path.join(temp_dir, "setup.json")) as h:
            assert json.load(h)
