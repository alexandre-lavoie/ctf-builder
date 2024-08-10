import argparse
import dataclasses
import typing

from ...build.attachment import BuildAttachment
from ...build.deployer import BuildDeployer
from ...build.flag import BuildFlag
from ...build.translation import BuildTranslation
from ...config import CHALLENGE_BASE_PORT, CHALLENGE_HOST, CHALLENGE_MAX_PORTS
from ...ctfd import CTFdAPI, ctfd_errors
from ...error import BuildError, DeployError, LibError
from ...schema import PortProtocol, Track, Translation
from ..common import (
    CliContext,
    WrapContext,
    cli_challenge_wrapper,
    get_challenge_index,
    get_challenges,
)


@dataclasses.dataclass(frozen=True)
class Args:
    api_key: str
    url: str = dataclasses.field(default="http://localhost:8000")
    port: int = dataclasses.field(default=CHALLENGE_BASE_PORT)
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    session: CTFdAPI
    port: int


@dataclasses.dataclass
class ChallengeRequest:
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


def build_challenge_requests(
    track: Track, context: Context
) -> typing.Tuple[typing.List[ChallengeRequest], typing.Sequence[LibError]]:
    output = []
    errors = []

    base_port = (
        context.port + get_challenge_index(context.challenge_path) * CHALLENGE_MAX_PORTS
    )

    deploy_ports_list: typing.List[typing.List[typing.Tuple[PortProtocol, int]]] = []
    for deployer in track.deploy:
        ports: typing.List[typing.Tuple[PortProtocol, int]] = []
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
            connection_info = protocol.connection_string(
                host=CHALLENGE_HOST,
                port=port_value,
                path=challenge.host.path,
            )
        else:
            connection_info = None

        output.append(
            ChallengeRequest(
                name=name,
                description=description,
                category=challenge.category,
                value=challenge.value,
                connection_info=connection_info,
            )
        )

    return output, errors


def send_challenge_requests(
    reqs: typing.List[ChallengeRequest], context: Context
) -> typing.Tuple[typing.List[int], typing.Sequence[LibError]]:
    output = []
    errors: typing.List[LibError] = []

    for i, req in enumerate(reqs):
        res = context.session.get("/challenges", data={"name": req.name})

        challenge_id = None
        if res.status_code == 200:
            data = res.json()["data"]

            if len(data) == 1:
                challenge_api = data[0]
                challenge_id = challenge_api["id"]

        if challenge_id:
            res = context.session.patch(
                f"/challenges/{challenge_id}",
                data=dataclasses.asdict(req),
            )
        else:
            res = context.session.post(
                "/challenges",
                data=dataclasses.asdict(req),
            )

        if res_errors := ctfd_errors(res, context=f"Challenge {i}"):
            errors += res_errors
            continue

        output.append(res.json()["data"]["id"])

    return output, errors


@dataclasses.dataclass
class FlagRequest:
    challenge: int
    content: str
    type: str
    data: typing.Optional[str] = dataclasses.field(default=None)


def build_flag_requests(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[FlagRequest], typing.Sequence[LibError]]:
    output = []
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        for flag_def in challenge.flags:
            for flag in BuildFlag.build(context.challenge_path, flag_def):
                output.append(
                    FlagRequest(
                        challenge=id,
                        content=flag,
                        type="regex" if flag_def.regex else "static",
                        data="" if flag_def.case_sensitive else "case_insensitive",
                    )
                )

    return output, errors


def send_flag_requests(
    reqs: typing.List[FlagRequest], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    challenge_ids: typing.Set[int] = set()
    for req in reqs:
        challenge_ids.add(req.challenge)

    for challenge_id in challenge_ids:
        res = context.session.get("/flags", data={"challenge_id": challenge_id})

        if res.status_code != 200:
            continue

        for flag_api in res.json()["data"]:
            context.session.delete(f"/flags/{flag_api['id']}")

    for i, req in enumerate(reqs):
        res = context.session.post(
            "/flags",
            data=dataclasses.asdict(req),
        )

        if res_errors := ctfd_errors(
            res, context=f"Flag {i} of challenge {req.challenge}"
        ):
            errors += res_errors
            continue

    return errors


@dataclasses.dataclass
class AttachmentRequest:
    challenge: int
    type: str
    file_name: str
    file_data: typing.BinaryIO


def build_attachment_requests(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[AttachmentRequest], typing.Sequence[LibError]]:
    errors: typing.List[LibError] = []
    reqs: typing.List[AttachmentRequest] = []

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

            reqs.append(
                AttachmentRequest(
                    challenge=id, type="challenge", file_name=name, file_data=fh
                )
            )

    return reqs, errors


def send_attachment_requests(
    reqs: typing.Sequence[AttachmentRequest], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    challenge_ids: typing.Set[int] = set()
    for req in reqs:
        challenge_ids.add(req.challenge)

    for challenge_id in challenge_ids:
        res = context.session.get(f"/challenges/{challenge_id}/files")

        if res.status_code != 200:
            continue

        for files_api in res.json()["data"]:
            context.session.delete(f"/files/{files_api['id']}")

    for i, req in enumerate(reqs):
        res = context.session.post_data(
            "/files",
            data={"challenge": req.challenge, "type": req.type},
            files={"file": (req.file_name, req.file_data)},
        )

        if res_errors := ctfd_errors(
            res, context=f"Attachment {i} of challenge {req.challenge}"
        ):
            errors += res_errors
            continue

    return errors


@dataclasses.dataclass
class HintRequest:
    challenge_id: int
    content: str
    cost: int


def build_hint_requests(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[HintRequest], typing.Sequence[LibError]]:
    errors: typing.List[LibError] = []

    reqs: typing.List[HintRequest] = []
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

            reqs.append(HintRequest(challenge_id=id, content=content, cost=hint.cost))

    return reqs, errors


def send_hint_requests(
    reqs: typing.Sequence[HintRequest], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    challenge_ids: typing.Set[int] = set()
    for req in reqs:
        challenge_ids.add(req.challenge_id)

    for challenge_id in challenge_ids:
        res = context.session.get("/hints", data={"challenge_id": challenge_id})

        if res.status_code != 200:
            continue

        for flag_api in res.json()["data"]:
            context.session.delete(f"/hints/{flag_api['id']}")

    for i, req in enumerate(reqs):
        res = context.session.post(
            "/hints",
            data=dataclasses.asdict(req),
        )

        if res_errors := ctfd_errors(
            res, context=f"Hint {i} of challenge {req.challenge_id}"
        ):
            errors += res_errors
            continue

    return errors


def send_references(
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
            res = context.session.patch(
                f"/challenges/{id}",
                data={
                    "requirements": {"anonymize": True, "prerequisites": prerequisites}
                },
            )

            if res_errors := ctfd_errors(res, context=f"Challenge {id}"):
                errors += res_errors
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

            res = context.session.patch(
                f"/challenges/{id}",
                {"next_id": ids[challenge.next]},
            )

            if res_errors := ctfd_errors(res, context=f"Challenge {id}"):
                errors += res_errors
                continue

    return errors


def deploy_challenge(track: Track, context: Context) -> typing.Sequence[LibError]:
    create_requests, errors = build_challenge_requests(track, context)
    if errors:
        return errors

    challenge_ids, errors = send_challenge_requests(create_requests, context)
    if errors:
        return errors

    all_errors: typing.List[LibError] = []

    flag_requests, errors = build_flag_requests(track, challenge_ids, context)
    all_errors += errors
    all_errors += send_flag_requests(flag_requests, context)

    attachment_requests, errors = build_attachment_requests(
        track, challenge_ids, context
    )
    all_errors += errors
    all_errors += send_attachment_requests(attachment_requests, context)

    hint_requests, errors = build_hint_requests(track, challenge_ids, context)
    all_errors += errors
    all_errors += send_hint_requests(hint_requests, context)

    all_errors += send_references(track, challenge_ids, context)

    return all_errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument("-k", "--api_key", help="API Key", required=True)
    parser.add_argument(
        "-u", "--url", help="URL for CTFd", default="http://localhost:8000"
    )
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
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
        session=CTFdAPI(args.url, args.api_key),
        port=args.port,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=deploy_challenge,
        console=cli_context.console,
    )
