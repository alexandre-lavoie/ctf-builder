import argparse
import dataclasses
import typing

from ..error import LibError
from ..models.challenge import Track
from .common import CliContext, WrapContext, cli_challenge_wrapper, get_challenges


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    pass


def schema(track: Track, context: Context) -> typing.Sequence[LibError]:
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


def cli(args: Args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=schema,
        console=cli_context.console,
    )
