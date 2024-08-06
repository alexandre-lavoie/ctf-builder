import argparse
import dataclasses
import glob
import os
import os.path
import typing

from ..error import LibError
from ..schema import Track
from .common import CliContext, WrapContext, cli_challenge_wrapper


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    pass


def schema(track: Track, context: Context) -> typing.Sequence[LibError]:
    return []


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
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


def cli(args: Args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge,
        context=context,
        callback=schema,
        console=cli_context.console,
    )
