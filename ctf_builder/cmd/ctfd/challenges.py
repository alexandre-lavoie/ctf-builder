import argparse
import dataclasses
import glob
import json
import os
import os.path
import typing

import requests

from ...build import *
from ...config import CHALLENGE_BASE_PORT, CHALLENGE_MAX_PORTS, CHALLENGE_HOST
from ...error import LibError, BuildError, SkipError, print_errors, get_exit_status
from ...parse import parse_track
from ...schema import *

def build_translation(root: str, translations: typing.Sequence[Translation]) -> typing.Optional[str]:
    priority_texts = []
    for translation in translations:
        db = BuildTranslation.get(translation)
        if db is None:
            return None

        text = db.build(root, translation)
        if text is None:
            return None

        priority_texts.append((db.priority(), text))

    return "\n\n-----\n\n".join([v for _, v in sorted(priority_texts)])

@dataclasses.dataclass
class ChallengeCreateRequest:
    category: str
    description: str
    name: str
    value: int
    state: str = dataclasses.field(default="visible")
    type: str = dataclasses.field(default="standard")
    connection_info: typing.Optional[str] = dataclasses.field(default=None)

def build_create_challenges(root: str, track: Track, port: int) -> typing.Tuple[typing.List[ChallengeCreateRequest], typing.Sequence[LibError]]:
    output = []
    errors = []

    deploy_ports: typing.List[typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]] = []
    for deployer in track.deploy:
        bd = BuildDeployer.get(deployer)
        if bd is None:
            errors.append(BuildError(f"challenge {i} has an unhandled deployer"))
            deploy_ports.append([])
            continue

        deploy_ports.append(bd.public_ports(deployer, port))

    for i, challenge in enumerate(track.challenges):
        name = track.name
        if challenge.name:
            name += f" - {challenge.name}"

        description = build_translation(root, challenge.descriptions)
        if description is None:
            errors.append(BuildError(f"challenge {i} has an invalid description"))
            continue

        if challenge.host is not None:
            if challenge.host.index < 0 or challenge.host.index >= len(deploy_ports):
                errors.append(BuildError(f"challenge {i} has an invalid host index"))
                continue

            for deploy_port in deploy_ports[challenge.host.index]:
                if deploy_port is None:
                    continue

                break
            else:
                errors.append(BuildError(f"challenge {i} has an invalid host with no public ports"))
                continue

            protocol, port_value = deploy_port
            if protocol is PortProtocol.HTTP:
                connection_info = f"http://{CHALLENGE_HOST}:{port_value}{challenge.host.path}"
            elif protocol is PortProtocol.HTTPS:
                connection_info = f"https://{CHALLENGE_HOST}:{port_value}{challenge.host.path}"
            elif protocol is PortProtocol.TCP:
                connection_info = f"nc {CHALLENGE_HOST} {port_value}"
            elif protocol is PortProtocol.UDP:
                connection_info = f"nc -u {CHALLENGE_HOST} {port_value}"
        else:
            connection_info = None

        output.append(
            ChallengeCreateRequest(
                name=name,
                description=description,
                category=challenge.category,
                value=challenge.value,
                connection_info=connection_info
            )
        )

    return output, errors

def post_create_challenges(url: str, api_key: str, reqs: typing.List[ChallengeCreateRequest]) -> typing.Tuple[typing.List[int], typing.Sequence[LibError]]:
    output = []
    errors = []

    for i, req in enumerate(reqs):
        res = requests.post(f"{url}/api/v1/challenges",
            headers={
                "Authorization": f"Token {api_key}"
            },
            json=dataclasses.asdict(req)
        )

        if res.status_code != 200:
            errors.append(BuildError(f"failed to create challenge {i}"))
            continue

        data = res.json()["data"]
        id = data["id"]

        output.append(id)

    return output, errors

@dataclasses.dataclass
class FlagCreateRequest:
    challenge: int
    content: str
    type: str
    data: str = dataclasses.field(default=None)

def build_create_flags(root: str, track: Track, ids: typing.List[int]) -> typing.Tuple[typing.List[FlagCreateRequest], typing.Sequence[LibError]]:
    output = []
    errors = []

    for id, challenge in zip(ids, track.challenges):
        for flag in challenge.flags:
            for content in BuildFlag.build(root, flag):
                output.append(
                    FlagCreateRequest(
                        challenge=id,
                        content=content,
                        type="regex" if flag.regex else "static",
                        data="" if flag.case_sensitive else "case_insensitive"
                    )
                )

    return output, errors

def post_create_flags(url: str, api_key: str, reqs: typing.List[FlagCreateRequest]) -> typing.Sequence[LibError]:
    errors = []

    for i, req in enumerate(reqs):
        res = requests.post(f"{url}/api/v1/flags",
            headers={
                "Authorization": f"Token {api_key}"
            },
            json=dataclasses.asdict(req)
        )

        if res.status_code != 200:
            errors.append(BuildError(f"failed to build flag in challenge {i}"))
            continue

    return errors

def post_attachments(root: str, url: str, api_key: str, track: Track, ids: typing.List[int]) -> typing.Sequence[LibError]:
    errors = []

    for id, challenge in zip(ids, track.challenges):
        for attachment in challenge.attachments:
            ab = BuildAttachment.get(attachment)
            if ab is None:
                errors.append(BuildError(f"attachment is not supported for challenge {id}"))
                continue

            out = ab.build(root, attachment)
            if out is None:
                errors.append(BuildError(f"attachment is not valid for challenge {id}"))
                continue

            name, fh = out

            res = requests.post(f"{url}/api/v1/files",
                headers={
                    "Authorization": f"Token {api_key}"
                },
                data={
                    "challenge": id,
                    "type": "challenge"
                },
                files={
                    "file": (name, fh)
                }
            )

            if res.status_code != 200:
                errors.append(BuildError(f"failed to build attachment in challenge {id}"))
                continue

    return errors

def post_hints(root: str, url: str, api_key: str, track: Track, ids: typing.List[int]) -> typing.Sequence[LibError]:
    errors = []

    for id, challenge in zip(ids, track.challenges):
        for hint in challenge.hints:
            content = build_translation(root, hint.texts)
            if content is None:
                errors.append(BuildError(f"content in hint of challenge {id} is invalid"))
                continue

            res = requests.post(f"{url}/api/v1/hints",
                headers={
                    "Authorization": f"Token {api_key}"
                },
                json={
                    "challenge_id": id,
                    "content": content,
                    "cost": hint.cost
                }
            )

            if res.status_code != 200:
                errors.append(BuildError(f"failed to build hint in challenge {id}"))
                continue

    return errors

def patch_references(url: str, api_key: str, track: Track, ids: typing.List[int]) -> typing.Sequence[LibError]:
    errors = []

    for id, challenge in zip(ids, track.challenges):
        prerequisites = []
        for offset in challenge.prerequisites:
            if offset >= len(ids):
                errors.append(f"offset {offset} for prerequisites is out of range for challenge {id}")
                continue

            prerequisites.append(ids[offset])

        if prerequisites:
            res = requests.patch(f"{url}/api/v1/challenges/{id}",
                headers={
                    "Authorization": f"Token {api_key}"
                },
                json={
                    "requirements": {
                        "anonymize": True,
                        "prerequisites": prerequisites
                    }
                }
            )

            if res.status_code != 200:
                errors.append(BuildError(f"failed to patch requirements in challenge {id}"))
                continue

        if challenge.next is not None:
            if challenge.next >= len(ids):
                errors.append(f"next {challenge.next} is out of range for challenge {id}")
                continue

            res = requests.patch(f"{url}/api/v1/challenges/{id}",
                headers={
                    "Authorization": f"Token {api_key}"
                },
                json={
                    "next_id": ids[challenge.next]
                }
            )

            if res.status_code != 200:
                errors.append(BuildError(f"failed to patch next_id in challenge {id}"))
                continue

    return errors

def build_challenge(json_path: str, url: str, api_key: str, skip_active: bool, port: int) -> typing.Sequence[typing.Union[LibError]]:
    if not os.path.exists(json_path):
        return [BuildError("file not found")]

    if not os.path.isfile(json_path):
        return [BuildError("not a file")]

    try:
        with open(json_path) as h:
            data = json.load(h)
    except:
        return [BuildError("invalid JSON")]

    track, errors = parse_track(data)
    if errors:
        return errors

    if not skip_active and not track.active:
        return [SkipError()] 

    root = os.path.dirname(json_path)

    create_requests, errors = build_create_challenges(root, track, port)
    if errors:
        return errors

    challenge_ids, errors = post_create_challenges(url, api_key, create_requests)
    if errors:
        return errors

    all_errors = []

    flag_requests, errors = build_create_flags(root, track, challenge_ids)
    all_errors += errors

    all_errors += post_create_flags(url, api_key, flag_requests)

    all_errors += post_attachments(root, url, api_key, track, challenge_ids)

    all_errors += post_hints(root, url, api_key, track, challenge_ids)

    all_errors += patch_references(url, api_key, track, challenge_ids)

    return all_errors

def challenge_iter(root: str) -> typing.Sequence[str]:
    return glob.glob("**/challenge.json", root_dir=root, recursive=True)

def build_challenges(root: str, url: str, api_key: str, port: int) -> typing.Mapping[str, typing.Sequence[BuildError]]:
    out = {}
    for file in challenge_iter(root):
        path = os.path.join(root, file)

        out[path] = build_challenge(path, url, api_key, skip_active=False, port=port)

        port += CHALLENGE_MAX_PORTS

    return out

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-k", "--api_key", help="API Key", required=True)
    parser.add_argument("-u", "--url", help="URL for CTFd", default="http://localhost:8000")
    parser.add_argument("-c", "--challenge", choices=challenges, help="Name of challenge to build", default=None)
    parser.add_argument("-p", "--port", type=int, help="Starting port for challenges", default=CHALLENGE_BASE_PORT)

def cli(args, root_directory: str) -> bool:
    challenge_directory = os.path.join(root_directory, "challenges")

    port = args.port

    all_errors = []
    if args.challenge:
        path = os.path.join(challenge_directory, args.challenge, "challenge.json")

        for name in challenge_iter(challenge_directory):
            if args.challenge == os.path.basename(os.path.dirname(name)):
                break

            port += CHALLENGE_MAX_PORTS

        all_errors = build_challenge(path, args.url, args.api_key, skip_active=True, port=port)

        print_errors(None, all_errors)
    else:
        for path, errors in build_challenges(challenge_directory, args.url, args.api_key, port).items():
            all_errors += errors
            print_errors(os.path.basename(os.path.dirname(path)), errors)

    return get_exit_status(all_errors)
