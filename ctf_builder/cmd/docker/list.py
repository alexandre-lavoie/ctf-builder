import argparse
import dataclasses
import io
import os.path
import typing

import docker
import docker.models.networks

from ...docker import to_docker_tag
from ...error import LibError, SkipError
from ...models.challenge import Track
from ..common import CliContext, WrapContext, cli_challenge_wrapper, get_challenges


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    output: typing.Optional[str] = dataclasses.field(default=None)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )
    output: typing.List[str] = dataclasses.field(default_factory=list)


def list_(track: Track, context: Context) -> typing.Sequence[LibError]:
    if not track.deploy:
        return [SkipError()]

    for i, _ in enumerate(track.deploy):
        context.output.append(to_docker_tag(f"{track.tag or track.name}-{i}"))

    return []


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
        default=[],
    )
    parser.add_argument("-o", "--output", help="Output file path", default=None)


def cli(args: Args, cli_context: CliContext) -> bool:
    output: typing.List[str] = []

    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        docker_client=cli_context.docker_client,
        output=output,
    )

    if not cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=list_,
        console=cli_context.console,
    ):
        return False

    if args.output:
        with open(args.output, "w") as h:
            for v in output:
                h.write(f"{v}\n")
    else:
        print()

        for v in output:
            print(v)

    return True
