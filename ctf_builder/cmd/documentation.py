import argparse
import dataclasses
import json
import os.path

from ..models.challenge import Track
from .common import CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    output: str


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory",
        default=os.path.join(root_directory, "doc"),
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    if not os.path.isdir(os.path.dirname(args.output)):
        return False

    os.makedirs(args.output, exist_ok=True)

    challenge_json = os.path.join(args.output, "challenge.json")

    with open(challenge_json, "w") as h:
        json.dump(Track.model_json_schema(), h, indent=2)

    return True
