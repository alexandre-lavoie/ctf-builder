import argparse
import dataclasses
import json
import os.path
import time
import typing

from ...ctfd.api import CTFdAPI
from ...ctfd.models import CTFdSetup
from ...error import LibError, disable_ssl_warnings, get_exit_status, print_errors
from ..common import CliContext


@dataclasses.dataclass
class Args:
    name: str
    email: str
    password: str
    file: str
    url: str = dataclasses.field(default="http://localhost:8000")
    skip_ssl: bool = dataclasses.field(default=False)


@dataclasses.dataclass
class Context:
    password: str
    url: str
    name: str
    email: str
    file: str
    skip_ssl: bool = dataclasses.field(default=False)


def setup(context: Context) -> typing.Sequence[LibError]:
    with open(context.file, "r") as h:
        config = json.load(h)

    ctfd_setup = CTFdSetup(**config)

    ctfd_setup.name = context.name
    ctfd_setup.email = context.email
    ctfd_setup.password = context.password

    return CTFdAPI.setup(
        context.url,
        ctfd_setup,
        root=os.path.dirname(context.file),
        verify_ssl=not context.skip_ssl,
    )


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-p", "--password", help="Admin account password", required=True
    )
    parser.add_argument(
        "-u", "--url", help="URL for CTFd", default="http://localhost:8000"
    )
    parser.add_argument("-n", "--name", help="Admin account name", default="admin")
    parser.add_argument(
        "-e", "--email", help="Admin account email", default="admin@ctfd.io"
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Config file path",
        default=os.path.join(root_directory, "ctfd", "setup.json"),
    )
    parser.add_argument(
        "-s",
        "--skip_ssl",
        action="store_true",
        help="Skip SSL check",
        default=False,
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    if args.skip_ssl:
        disable_ssl_warnings()

    start_time = time.time()
    errors = setup(
        Context(
            url=args.url,
            file=args.file,
            name=args.name,
            email=args.email,
            password=args.password,
            skip_ssl=args.skip_ssl,
        )
    )
    end_time = time.time()

    print_errors(
        prefix=["setup"],
        errors=errors,
        console=cli_context.console,
        elapsed_time=end_time - start_time,
    )

    return get_exit_status(errors)
