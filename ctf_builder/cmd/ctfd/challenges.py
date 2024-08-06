import argparse
import dataclasses
import glob
import os
import os.path
import typing

import requests

from ...build import BuildTranslation, BuildDeployer, BuildFlag, BuildAttachment
from ...config import CHALLENGE_BASE_PORT, CHALLENGE_MAX_PORTS, CHALLENGE_HOST
from ...error import LibError, BuildError, DeployError
from ...schema import Track, Translation

from ..common import CliContext

from ..common import (
    WrapContext,
    cli_challenge_wrapper,
    get_challenge_index,
    build_connection_string,
)


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    url: str
    port: int
    challenge: typing.Sequence[str]


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    url: str
    api_key: str
    port: int


@dataclasses.dataclass
class ChallengeCreateRequest:
    category: str
    description: str
    name: str
    value: int
    state: str = dataclasses.field(default="visible")
    type: str = dataclasses.field(default="standard")
    connection_info: typing.Optional[str] = dataclasses.field(default=None)


def build_translation(
    root: str, translations: typing.Sequence[Translation]
) -> typing.Optional[str]:
    priority_texts = []
    for translation in translations:
        build = BuildTranslation.get(translation)

        if (text := build.build(root, translation)) is None:
            return None

        priority_texts.append((build.priority(), text))

    return "\n\n-----\n\n".join([v for _, v in sorted(priority_texts)])


def build_create_challenges(
    track: Track, context: Context
) -> typing.Tuple[typing.List[ChallengeCreateRequest], typing.Sequence[LibError]]:
    output = []
    errors = []

    base_port = (
        context.port + get_challenge_index(context.challenge_path) * CHALLENGE_MAX_PORTS
    )

    deploy_ports_list = []
    for deployer in track.deploy:
        ports = []
        for protocol, _ in BuildDeployer.get(deployer).ports(deployer):
            ports.append((protocol, base_port))
            base_port += 1
        deploy_ports_list.append(ports)

    for i, challenge in enumerate(track.challenges):
        name = track.name
        if challenge.name:
            name += f" - {challenge.name}"

        description = build_translation(context.challenge_path, challenge.descriptions)
        if description is None:
            errors.append(
                BuildError(context=f"Challenge {i}", msg="has an invalid description")
            )
            continue

        if challenge.host is not None:
            if challenge.host.index < 0 or challenge.host.index >= len(
                deploy_ports_list
            ):
                errors.append(
                    BuildError(
                        context=f"Challenge {i}", msg="has an invalid host index"
                    )
                )
                continue

            deploy_ports = deploy_ports_list[challenge.host.index]
            if not deploy_ports:
                errors.append(
                    BuildError(
                        context=f"Challenge {i}",
                        msg="host has no exposed ports, remove link if this is intentional",
                    )
                )
                continue

            protocol, port_value = deploy_ports[0]
            connection_info = build_connection_string(
                host=CHALLENGE_HOST,
                protocol=protocol,
                port=port_value,
                path=challenge.host.path,
            )
        else:
            connection_info = None

        output.append(
            ChallengeCreateRequest(
                name=name,
                description=description,
                category=challenge.category,
                value=challenge.value,
                connection_info=connection_info,
            )
        )

    return output, errors


def post_create_challenges(
    reqs: typing.List[ChallengeCreateRequest], context: Context
) -> typing.Tuple[typing.List[int], typing.Sequence[LibError]]:
    output = []
    errors = []

    for i, req in enumerate(reqs):
        res = requests.post(
            f"{context.url}/api/v1/challenges",
            headers={"Authorization": f"Token {context.api_key}"},
            json=dataclasses.asdict(req),
        )

        if res.status_code != 200:
            errors.append(
                BuildError(
                    context=f"Challenge {i}",
                    msg="failed to create",
                    error=ValueError(res.json()["message"]),
                )
            )
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
    data: typing.Optional[str] = dataclasses.field(default=None)


def build_create_flags(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[FlagCreateRequest], typing.Sequence[LibError]]:
    output = []
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        for flag in challenge.flags:
            for content in BuildFlag.build(context.challenge_path, flag):
                output.append(
                    FlagCreateRequest(
                        challenge=id,
                        content=content,
                        type="regex" if flag.regex else "static",
                        data="" if flag.case_sensitive else "case_insensitive",
                    )
                )

    return output, errors


def post_create_flags(
    reqs: typing.List[FlagCreateRequest], context: Context
) -> typing.Sequence[LibError]:
    errors = []

    for i, req in enumerate(reqs):
        res = requests.post(
            f"{context.url}/api/v1/flags",
            headers={"Authorization": f"Token {context.api_key}"},
            json=dataclasses.asdict(req),
        )

        if res.status_code != 200:
            errors.append(
                BuildError(
                    context=f"Flag {i} of challenge {req.challenge}",
                    msg="failed to created",
                    error=ValueError(res.json()["message"]),
                )
            )
            continue

    return errors


def post_attachments(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        for i, attachment in enumerate(challenge.attachments):
            if (
                out := BuildAttachment.get(attachment).build(
                    context.challenge_path, attachment
                )
            ) is None:
                errors.append(
                    BuildError(
                        context=f"Attachment {i} of challenge {id}", msg="is not valid"
                    )
                )
                continue

            name, fh = out

            res = requests.post(
                f"{context.url}/api/v1/files",
                headers={"Authorization": f"Token {context.api_key}"},
                data={"challenge": id, "type": "challenge"},
                files={"file": (name, fh)},
            )

            if res.status_code != 200:
                errors.append(
                    DeployError(
                        context=f"Attachment {i} of challenge {id}",
                        msg="failed to create",
                        error=ValueError(res.json()["message"]),
                    )
                )
                continue

    return errors


def post_hints(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        for i, hint in enumerate(challenge.hints):
            content = build_translation(context.challenge_path, hint.texts)
            if content is None:
                errors.append(
                    BuildError(
                        context=f"Hint {i} of challenge {id}", msg="is not valid"
                    )
                )
                continue

            res = requests.post(
                f"{context.url}/api/v1/hints",
                headers={"Authorization": f"Token {context.api_key}"},
                json={"challenge_id": id, "content": content, "cost": hint.cost},
            )

            if res.status_code != 200:
                errors.append(
                    DeployError(
                        context=f"Hint {i} of challenge {id}",
                        msg="failed to create",
                        error=ValueError(res.json()["message"]),
                    )
                )
                continue

    return errors


def patch_references(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        prerequisites = []
        for offset in challenge.prerequisites:
            if offset >= len(ids):
                errors.append(
                    BuildError(
                        context=f"Challenge {id}",
                        msg="offset for prerequisites is out of range",
                    )
                )
                continue

            prerequisites.append(ids[offset])

        if prerequisites:
            res = requests.patch(
                f"{context.url}/api/v1/challenges/{id}",
                headers={"Authorization": f"Token {context.api_key}"},
                json={
                    "requirements": {"anonymize": True, "prerequisites": prerequisites}
                },
            )

            if res.status_code != 200:
                errors.append(
                    DeployError(
                        context=f"Challenge {id}",
                        msg="failed to update prerequisites",
                        error=ValueError(res.json()["message"]),
                    )
                )
                continue

        if challenge.next is not None:
            if challenge.next < 0 or challenge.next >= len(ids):
                errors.append(
                    DeployError(
                        context=f"Challenge {id}",
                        msg="next is out of range",
                    )
                )
                continue

            res = requests.patch(
                f"{context.url}/api/v1/challenges/{id}",
                headers={"Authorization": f"Token {context.api_key}"},
                json={"next_id": ids[challenge.next]},
            )

            if res.status_code != 200:
                errors.append(
                    DeployError(
                        context=f"Challenge {id}",
                        msg="failed to update next",
                        error=ValueError(res.json()["message"]),
                    )
                )
                continue

    return errors


def deploy_challenge(track: Track, context: Context) -> typing.Sequence[LibError]:
    create_requests, errors = build_create_challenges(track, context)
    if errors:
        return errors

    challenge_ids, errors = post_create_challenges(create_requests, context)
    if errors:
        return errors

    all_errors: typing.List[LibError] = []

    flag_requests, errors = build_create_flags(track, challenge_ids, context)
    all_errors += errors

    all_errors += post_create_flags(flag_requests, context)
    all_errors += post_attachments(track, challenge_ids, context)
    all_errors += post_hints(track, challenge_ids, context)
    all_errors += patch_references(track, challenge_ids, context)

    return all_errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-k", "--api_key", help="API Key", required=True)
    parser.add_argument(
        "-u", "--url", help="URL for CTFd", default="http://localhost:8000"
    )
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=challenges,
        help="Name of challenge to build",
        default=[],
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Starting port for challenges",
        default=CHALLENGE_BASE_PORT,
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        url=args.url,
        api_key=args.api_key,
        port=args.port,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge,
        context=context,
        callback=deploy_challenge,
        console=cli_context.console,
    )
