import argparse
import dataclasses
import io
import os.path
import json
import re
import typing

import requests

@dataclasses.dataclass
class SetupFiles:
    ctf_logo: io.BytesIO = dataclasses.field(default=None)
    ctf_banner: io.BytesIO = dataclasses.field(default=None)
    ctf_small_icon: io.BytesIO = dataclasses.field(default=None)

    @classmethod
    def from_dict(cls, directory: str, data: typing.Dict) -> "SetupFiles":
        fields = {}

        for field in dataclasses.fields(cls):
            path = os.path.join(directory, data.get(field.name))

            if not (os.path.exists(path) and os.path.isfile(path)):
                continue

            fields[field.name] = open(path, "rb")

        return cls(**fields)

    def to_dict(self) -> typing.Dict:
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
    theme_color: str = dataclasses.field(default=None)
    start: str = dataclasses.field(default=None)
    end: str = dataclasses.field(default=None)
    nonce: str = dataclasses.field(default=None)
    team_size: int = dataclasses.field(default=0)

    @classmethod
    def from_dict(cls, data: typing.Dict) -> "SetupData":
        fields = {}

        for field in dataclasses.fields(cls):
            value = data.get(field.name)
            if value is None:
                continue

            fields[field.name] = field.type(value)

        return cls(**fields)
    
    def to_dict(self) -> typing.Dict:
        out = {}

        for field in dataclasses.fields(SetupData):
            out[field.name] = getattr(self, field.name)

        return out

@dataclasses.dataclass
class Setup:
    data: SetupData
    files: SetupFiles

    @classmethod
    def from_dict(cls, directory: str, data: typing.Dict) -> "Setup":
        return Setup(
            data=SetupData.from_dict(data),
            files=SetupFiles.from_dict(directory, data)
        )

    def to_dict(self) -> typing.Dict:
        return {
            "data": self.data.to_dict(),
            "files": self.files.to_dict()
        }

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

def build_setup(url: str, file: str, name: str, email: str, password: str) -> bool:
    setup = make_setup(file, name, email, password)

    sess = requests.Session()

    nonce = read_nonce(sess, url)
    if nonce is None:
        return False
    setup.data.nonce = nonce

    res = sess.post(f"{url}/setup", **setup.to_dict())

    return res.status_code == 200

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    parser.add_argument("-u", "--url", help="URL for CTFd", required=True)
    parser.add_argument("-n", "--name", help="Admin account name", default="admin")
    parser.add_argument("-e", "--email", help="Admin account email", default="admin@ctf.com")
    parser.add_argument("-p", "--password", help="Admin account password", required=True)
    parser.add_argument("-f", "--file", help="Config file path", default=os.path.join(root_directory, "ctfd", "setup.json"))

def cli(args, root_directory: str) -> bool:
    return build_setup(args.url, args.file, args.name, args.email, args.password)
