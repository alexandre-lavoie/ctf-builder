import argparse
import dataclasses
import os.path
import json
import re
import typing

import requests

from ...error import LibError, DeployError, print_errors, get_exit_status

from ..common import CliContext


@dataclasses.dataclass
class Args:
    password: str
    url: str
    name: str
    email: str
    file: str


@dataclasses.dataclass
class Context:
    password: str
    url: str
    name: str
    email: str
    file: str


@dataclasses.dataclass
class SetupFiles:
    ctf_logo: typing.Optional[typing.BinaryIO] = dataclasses.field(default=None)
    ctf_banner: typing.Optional[typing.BinaryIO] = dataclasses.field(default=None)
    ctf_small_icon: typing.Optional[typing.BinaryIO] = dataclasses.field(default=None)

    @classmethod
    def from_dict(
        cls, directory: str, data: typing.Dict[str, typing.Any]
    ) -> "SetupFiles":
        fields: typing.Dict[str, typing.BinaryIO] = {}

        for field in dataclasses.fields(cls):
            field_value = data.get(field.name)
            if not isinstance(field_value, str):
                continue

            path = os.path.join(directory, field_value)

            if not (os.path.exists(path) and os.path.isfile(path)):
                continue

            fields[field.name] = open(path, "rb")

        return cls(**fields)

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        out = {}

        for field in dataclasses.fields(SetupFiles):
            out[field.name] = getattr(self, field.name)

        return out


@dataclasses.dataclass
class SetupData:
    ctf_name: str
    ctf_description: str
    user_mode: str
    challenge_visibility: str
    score_visibility: str
    account_visibility: str
    registration_visibility: str
    verify_emails: bool
    name: str
    email: str
    password: str
    ctf_theme: str = dataclasses.field(default="core-beta")
    theme_color: str = dataclasses.field(default="")
    start: str = dataclasses.field(default="")
    end: str = dataclasses.field(default="")
    nonce: str = dataclasses.field(default="")
    team_size: int = dataclasses.field(default=0)

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "SetupData":
        fields = {}

        for field in dataclasses.fields(cls):
            value = data.get(field.name)
            if value is None:
                continue

            fields[field.name] = field.type(value)

        return cls(**fields)

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        out = {}

        for field in dataclasses.fields(SetupData):
            out[field.name] = getattr(self, field.name)

        return out


@dataclasses.dataclass
class Setup:
    data: SetupData
    files: SetupFiles

    @classmethod
    def from_dict(cls, directory: str, data: typing.Dict[str, typing.Any]) -> "Setup":
        return Setup(
            data=SetupData.from_dict(data), files=SetupFiles.from_dict(directory, data)
        )

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        return {"data": self.data.to_dict(), "files": self.files.to_dict()}


NONCE_RE = re.compile(r"<input id=\"nonce\".+?value=\"(.+?)\">")


def read_nonce(sess: requests.Session, url: str) -> str:
    res = sess.get(f"{url}/setup")

    match = NONCE_RE.findall(res.text)

    return match[0] if match else None


def make_setup(file: str, name: str, email: str, password: str) -> Setup:
    with open(file, "r") as h:
        config = json.load(h)

    config["name"] = name
    config["email"] = email
    config["password"] = password

    directory = os.path.dirname(file)

    return Setup.from_dict(directory, config)


def setup(context: Context) -> typing.Sequence[LibError]:
    setup = make_setup(context.file, context.name, context.email, context.password)

    sess = requests.Session()

    nonce = read_nonce(sess, context.url)
    if nonce is None:
        return [DeployError(context="nonce", msg="failed to get")]
    setup.data.nonce = nonce

    res = sess.post(f"{context.url}/setup", **setup.to_dict())

    if res.status_code != 200:
        return [
            DeployError(
                context="setup",
                msg="failed to deploy",
                error=ValueError(res["message"]),
            )
        ]

    return []


def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    parser.add_argument(
        "-p", "--password", help="Admin account password", required=True
    )
    parser.add_argument(
        "-u", "--url", help="URL for CTFd", default="http://localhost:8000"
    )
    parser.add_argument("-n", "--name", help="Admin account name", default="admin")
    parser.add_argument(
        "-e", "--email", help="Admin account email", default="admin@ctf.com"
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Config file path",
        default=os.path.join(root_directory, "ctfd", "setup.json"),
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    errors = setup(
        Context(
            url=args.url,
            file=args.file,
            name=args.name,
            email=args.email,
            password=args.password,
        )
    )

    print_errors(errors=errors, console=cli_context.console)

    if cli_context.console:
        cli_context.console.print()

    return get_exit_status(errors)
