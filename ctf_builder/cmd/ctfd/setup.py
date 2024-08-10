import argparse
import dataclasses
import json
import os.path
import time
import typing

from ...ctfd.api import CTFdAPI
from ...ctfd.models import CTFdSetup
from ...error import LibError, get_exit_status, print_errors
from ..common import CliContext


@dataclasses.dataclass
class Args:
    name: str
    email: str
    password: str
    file: str
    url: str = dataclasses.field(default="http://localhost:8000")


@dataclasses.dataclass
class Context:
    password: str
    url: str
    name: str
    email: str
    file: str


def make_setup(file: str, name: str, email: str, password: str) -> CTFdSetup:
    with open(file, "r") as h:
        config = json.load(h)

    config["name"] = name
    config["email"] = email
    config["password"] = password

    return CTFdSetup(**config)


def setup(context: Context) -> typing.Sequence[LibError]:
    data = make_setup(context.file, context.name, context.email, context.password)

    return CTFdAPI.setup(context.url, data, root=os.path.dirname(context.file))


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


def cli(args: Args, cli_context: CliContext) -> bool:
    start_time = time.time()
    errors = setup(
        Context(
            url=args.url,
            file=args.file,
            name=args.name,
            email=args.email,
            password=args.password,
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
