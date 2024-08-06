import io
import json
import os.path

import docker

import rich.console

from ctf_builder.cmd.common import CliContext

from ctf_builder.cmd.schema import cli, Args


def test():
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    out_file = io.StringIO()
    assert cli(cli_context=context, args=Args(output=out_file))
    out_file.seek(0)

    json.load(out_file)
