import os.path
import tempfile

import docker
import rich.console

from ctf_builder.cmd.common import CliContext
from ctf_builder.cmd.k8s.build import Args as BuildArgs
from ctf_builder.cmd.k8s.build import cli as build_cli


def test_k8s_build() -> None:
    root_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sample"
    )

    context = CliContext(
        root_directory=root_directory,
        docker_client=docker.from_env(),
        console=rich.console.Console(quiet=True),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        assert build_cli(
            cli_context=context, args=BuildArgs(repository="repo", output=temp_dir)
        )
