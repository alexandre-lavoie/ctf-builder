import argparse
import dataclasses
import glob
import os
import os.path
import typing

import docker

from ..build import BuildBuilder, BuildContext
from ..error import LibError
from ..schema import Track

from .common import cli_challenge_wrapper, WrapContext, CliContext


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient]


def build(track: Track, context: Context) -> typing.Sequence[LibError]:
    errors = []
    for builder in track.build:
        errors += BuildBuilder.get(builder).build(
            builder=builder,
            context=BuildContext(
                path=context.challenge_path, docker_client=context.docker_client
            ),
        )

    return errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=challenges,
        help="Name of challenge",
        default=[],
    )


def cli(args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        docker_client=docker.from_env(),
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge,
        context=context,
        callback=build,
        console=cli_context.console,
    )
