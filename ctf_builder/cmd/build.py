import argparse
import dataclasses
import typing

import docker

from ..error import LibError, SkipError
from ..models.build.base import BuildContext
from ..models.challenge import Track
from .common import CliContext, WrapContext, cli_challenge_wrapper, get_challenges


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient]


def build(track: Track, context: Context) -> typing.Sequence[LibError]:
    if not track.build:
        return [SkipError()]

    errors: typing.List[LibError] = []
    for builder in track.build:
        errors += builder.build(
            BuildContext(
                root=context.challenge_path, docker_client=context.docker_client
            ),
        )

    return errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
        default=[],
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        docker_client=cli_context.docker_client,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=build,
        console=cli_context.console,
    )
