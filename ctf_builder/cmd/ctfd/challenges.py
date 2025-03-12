import argparse
import dataclasses
import typing

from ...config import CHALLENGE_BASE_PORT, CHALLENGE_MAX_PORTS
from ...ctfd.api import CTFdAPI
from ...ctfd.models import (
    CTFdAccessToken,
    CTFdChallenge,
    CTFdChallengeRequirements,
    CTFdFileUpload,
    CTFdFileUploadType,
    CTFdFlag,
    CTFdFlagData,
    CTFdFlagType,
    CTFdHint,
)
from ...ctfd.session import CTFdSession
from ...error import BuildError, DeployError, LibError, disable_ssl_warnings
from ...models.attachment import AttachmentContext
from ...models.challenge import Track
from ...models.flag import FlagContext
from ...models.port import ConnectionContext, Port
from ...models.text import Text, TextContext
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
    host: typing.Optional[str] = dataclasses.field(default=None)
    port: int = dataclasses.field(default=CHALLENGE_BASE_PORT)
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    skip_ssl: bool = dataclasses.field(default=False)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    api: CTFdAPI
    port: int
    host: typing.Optional[str] = dataclasses.field(default=None)


def build_challenges(
    track: Track, context: Context
) -> typing.Tuple[typing.List[CTFdChallenge], typing.Sequence[LibError]]:
    output = []
    errors = []

    base_port = (
        context.port + get_challenge_index(context.challenge_path) * CHALLENGE_MAX_PORTS
    )

    deploy_ports_list: typing.List[typing.List[typing.Tuple[Port, int]]] = []
    for deployer in track.deploy:
        ports: typing.List[typing.Tuple[Port, int]] = []
        for port in deployer.get_ports():
            if not port.public:
                continue

            ports.append((port, base_port))
            base_port += 1
        deploy_ports_list.append(ports)

    for i, challenge in enumerate(track.challenges):
        name = track.name
        if challenge.name:
            name += f" - {challenge.name}"

        if (
            description := Text.build_many(
                challenge.descriptions, TextContext(root=context.challenge_path)
            )
        ) is None:
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

            port, port_value = deploy_ports[0]
            connection_info = port.connection_string(
                ConnectionContext(
                    host=context.host or context.api.session.hostname(),
                    port=port_value,
                    path=challenge.host.path,
                )
            )
        else:
            connection_info = None

        output.append(
            CTFdChallenge(
                id=-1,
                name=name,
                description=description,
                category=challenge.category,
                value=challenge.value,
                connection_info=connection_info,
            )
        )

    return output, errors


def send_challenges(
    reqs: typing.List[CTFdChallenge], context: Context
) -> typing.Tuple[typing.List[int], typing.Sequence[LibError]]:
    output = []
    errors: typing.List[LibError] = []

    for req in reqs:
        res_many, res_errors = context.api.get_challenge_by_name(req.name or "")

        challenge_id = None
        if res_many:
            challenge_id = res_many[0].id

        if challenge_id:
            req.id = challenge_id

            res, res_errors = context.api.update_challenge(req)
        else:
            res, res_errors = context.api.create_challenge(req)

        if res is None:
            errors += res_errors
            continue

        output.append(res.id)

    return output, errors


def build_flags(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[CTFdFlag], typing.Sequence[LibError]]:
    output = []
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        for flag_def in challenge.flags:
            for flag in flag_def.build(FlagContext(root=context.challenge_path)):
                output.append(
                    CTFdFlag(
                        id=-1,
                        challenge_id=id,
                        content=flag,
                        type=(
                            CTFdFlagType.Regex
                            if flag_def.regex
                            else CTFdFlagType.Static
                        ),
                        data=(
                            CTFdFlagData.CaseSensitive
                            if flag_def.case_sensitive
                            else CTFdFlagData.CaseInsensitive
                        ),
                    )
                )

    return output, errors


def send_flags(
    reqs: typing.List[CTFdFlag], context: Context
) -> typing.Sequence[LibError]:
    challenge_ids: typing.Set[int] = set()
    for req in reqs:
        if req.challenge_id is not None:
            challenge_ids.add(req.challenge_id)

    for challenge_id in challenge_ids:
        flags, _ = context.api.get_flags_in_challenge(challenge_id)

        if flags:
            for flag in flags:
                context.api.delete_flag(flag.id)

    errors: typing.List[LibError] = []
    for req in reqs:
        _, res_errors = context.api.create_flag(req)

        errors += res_errors

    return errors


def build_attachments(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[CTFdFileUpload], typing.Sequence[LibError]]:
    errors: typing.List[LibError] = []
    reqs: typing.List[CTFdFileUpload] = []

    for id, challenge in zip(ids, track.challenges):
        for i, attachment in enumerate(challenge.attachments):
            if (
                handle := attachment.build(
                    AttachmentContext(root=context.challenge_path)
                )
            ) is None:
                errors.append(
                    BuildError(
                        context=f"Attachment {i} of challenge {id}", msg="is not valid"
                    )
                )
                continue

            reqs.append(
                CTFdFileUpload(
                    challenge=id,
                    type=CTFdFileUploadType.Challenge,
                    file_name=handle.name,
                    file_data=handle.data,
                )
            )

    return reqs, errors


def send_attachments(
    reqs: typing.Sequence[CTFdFileUpload], context: Context
) -> typing.Sequence[LibError]:
    challenge_ids: typing.Set[int] = set()
    for req in reqs:
        challenge_ids.add(req.challenge)

    for challenge_id in challenge_ids:
        files, _ = context.api.get_files_in_challenge(challenge_id)

        if files:
            for file in files:
                context.api.delete_file(file.id)

    errors: typing.List[LibError] = []
    for req in reqs:
        _, res_errors = context.api.create_file(req)

        errors += res_errors

    return errors


def build_hints(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Tuple[typing.List[CTFdHint], typing.Sequence[LibError]]:
    errors: typing.List[LibError] = []

    reqs: typing.List[CTFdHint] = []
    for id, challenge in zip(ids, track.challenges):
        for i, hint in enumerate(challenge.hints):
            content = Text.build_many(
                hint.texts, TextContext(root=context.challenge_path)
            )
            if content is None:
                errors.append(
                    BuildError(
                        context=f"Hint {i} of challenge {id}", msg="is not valid"
                    )
                )
                continue

            reqs.append(
                CTFdHint(id=-1, challenge_id=id, content=content, cost=hint.cost)
            )

    return reqs, errors


def send_hints(
    reqs: typing.Sequence[CTFdHint], context: Context
) -> typing.Sequence[LibError]:
    challenge_ids: typing.Set[int] = set()
    for req in reqs:
        if req.challenge_id is not None:
            challenge_ids.add(req.challenge_id)

    for challenge_id in challenge_ids:
        hints, _ = context.api.get_hints_in_challenge(challenge_id)

        if hints:
            for hint in hints:
                context.api.delete_hint(hint.id)

    errors: typing.List[LibError] = []
    for req in reqs:
        _, res_errors = context.api.create_hint(req)

        errors += res_errors

    return errors


def send_references(
    track: Track, ids: typing.List[int], context: Context
) -> typing.Sequence[LibError]:
    errors: typing.List[LibError] = []

    for id, challenge in zip(ids, track.challenges):
        ctfd_challenge = CTFdChallenge(id=id)

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
            ctfd_challenge.requirements = CTFdChallengeRequirements(
                anonymize=True, prerequisites=prerequisites
            )

        if challenge.next is not None:
            if challenge.next < 0 or challenge.next >= len(ids):
                errors.append(
                    DeployError(
                        context=f"Challenge {id}",
                        msg="next is out of range",
                    )
                )
                continue

            ctfd_challenge.next_id = ids[challenge.next]

        if prerequisites or challenge.next:
            _, res_errors = context.api.update_challenge(ctfd_challenge)

            errors += res_errors

    return errors


def deploy_challenge(track: Track, context: Context) -> typing.Sequence[LibError]:
    create_requests, errors = build_challenges(track, context)
    if errors:
        return errors

    challenge_ids, errors = send_challenges(create_requests, context)
    if errors:
        return errors

    all_errors: typing.List[LibError] = []

    flag_requests, errors = build_flags(track, challenge_ids, context)
    all_errors += errors
    all_errors += send_flags(flag_requests, context)

    attachment_requests, errors = build_attachments(track, challenge_ids, context)
    all_errors += errors
    all_errors += send_attachments(attachment_requests, context)

    hint_requests, errors = build_hints(track, challenge_ids, context)
    all_errors += errors
    all_errors += send_hints(hint_requests, context)

    all_errors += send_references(track, challenge_ids, context)

    return all_errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument("-k", "--api_key", help="API Key", required=True)
    parser.add_argument(
        "-u", "--url", help="URL for CTFd", default="http://localhost:8000"
    )
    parser.add_argument(
        "-t",
        "--host",
        help="IP or domain for challenges (defaults to CTFd domain if not specified)",
        default=None,
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

    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        api=CTFdAPI(
            CTFdSession(
                url=args.url,
                access_token=CTFdAccessToken(id=-1, value=args.api_key),
                verify_ssl=not args.skip_ssl,
            )
        ),
        host=args.host,
        port=args.port,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=deploy_challenge,
        console=cli_context.console,
    )
