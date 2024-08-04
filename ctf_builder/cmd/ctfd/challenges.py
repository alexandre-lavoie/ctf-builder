import argparse
import dataclasses
import glob
import json
import os
import os.path
import typing

import requests

from ...build import *
from ...error import LibError, BuildError, SkipError, print_errors
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

def build_create_challenges(root: str, track: Track) -> typing.Tuple[typing.List[ChallengeCreateRequest], typing.Sequence[LibError]]:
    output = []
    errors = []

    for i, challenge in enumerate(track.challenges):
        name = track.name
        if challenge.name:
            name += f" - {challenge.name}"

        description = build_translation(root, challenge.descriptions)
        if description is None:
            errors.append(BuildError(f"challenge {i} has an invalid description"))
            continue

        output.append(
            ChallengeCreateRequest(
                name=name,
                description=description,
                category=challenge.category,
                value=challenge.value
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
            errors.append(BuildError(f"failed to build challenge {i}"))
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
                        type="regex" if flag.regex else "standard",
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
                    "next_id": challenge.next
                }
            )

            if res.status_code != 200:
                errors.append(BuildError(f"failed to patch next_id in challenge {id}"))
                continue

    return errors

def build_challenge(json_path: str, url: str, api_key: str, skip_active: bool) -> typing.Sequence[typing.Union[LibError]]:
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

    create_requests, errors = build_create_challenges(root, track)
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

def build_challenges(root: str, url: str, api_key: str) -> typing.Mapping[str, typing.Sequence[BuildError]]:
    out = {}
    for file in glob.glob("**/challenge.json", root_dir=root, recursive=True):
        path = os.path.join(root, file)

        out[path] = build_challenge(path, url, api_key, skip_active=False) 

    return out

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-u", "--url", help="URL for CTFd", required=True)
    parser.add_argument("-k", "--api_key", help="API Key", required=True)
    parser.add_argument("-c", "--challenge", choices=challenges, help="Name of challenge to build", default=None)

def cli(args, root_directory: str) -> bool:
    challenge_directory = os.path.join(root_directory, "challenges")

    if args.challenge:
        path = os.path.join(challenge_directory, args.challenge, "challenge.json")
        errors = build_challenge(path, args.url, args.api_key, skip_active=True)

        is_ok = False if errors else True
        print_errors(None, errors)
    else:
        is_ok = True
        for path, errors in build_challenges(challenge_directory, args.url, args.api_key).items():
            if errors:
                is_ok = False

            print_errors(path, errors)

    return is_ok
