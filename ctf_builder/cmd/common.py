import dataclasses
import glob
import json
import os.path
import threading
import time
import typing

import docker
import docker.errors
import docker.models.networks
import rich.console
import rich.progress

from ..config import CHALLENGE_MAX_PORTS
from ..error import BuildError, LibError, SkipError, get_exit_status, print_errors
from ..parse import parse_track
from ..schema import PortProtocol, Track


MAX_TCP_PORT = 65_535


@dataclasses.dataclass(frozen=True)
class WrapContext:
    challenge_path: str
    error_prefix: typing.List[str]
    skip_inactive: bool


WC = typing.TypeVar("WC", bound=WrapContext)


@dataclasses.dataclass(frozen=True)
class CliContext:
    root_directory: str
    docker_client: docker.DockerClient
    console: typing.Optional[rich.console.Console]


def port_generator(port: int) -> typing.Generator[typing.Optional[int], None, None]:
    max_port = min(port + CHALLENGE_MAX_PORTS, MAX_TCP_PORT)
    while True:
        if port < 0 or port > max_port:
            break

        yield port

        port += 1

    while True:
        yield None


def build_connection_string(
    host: str, port: int, protocol: PortProtocol, path: typing.Optional[str] = None
) -> str:
    if protocol is PortProtocol.HTTP:
        return f"http://{host}:{port}{path}"
    elif protocol is PortProtocol.HTTPS:
        return f"https://{host}:{port}{path}"
    elif protocol is PortProtocol.TCP:
        return f"nc {host} {port}"
    elif protocol is PortProtocol.UDP:
        return f"nc -u {host} {port}"

    assert False, f"unhandled {protocol}"


def get_network(
    client: docker.DockerClient, name: typing.Optional[str] = None
) -> typing.Optional[docker.models.networks.Network]:
    try:
        return client.networks.get(name)
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError:
        pass

    return None


def create_network(
    client: docker.DockerClient, name: typing.Optional[str] = None
) -> typing.Optional[docker.models.networks.Network]:
    try:
        return client.networks.create(name, driver="bridge")
    except docker.errors.APIError:
        return None


def get_create_network(
    client: docker.DockerClient, name: typing.Optional[str] = None
) -> typing.Optional[docker.models.networks.Network]:
    network = get_network(client, name)
    if network is not None:
        return network

    return create_network(client, name)


def get_challenges(root_directory: str) -> typing.Optional[typing.Sequence[str]]:
    if not os.path.isdir(root_directory):
        return []

    challenge_directory = os.path.join(root_directory, "challenges")
    if not os.path.isdir(challenge_directory):
        return None

    return [name for name in glob.glob("*", root_dir=challenge_directory)]


def get_challenge_index(challenge_path: str) -> int:
    challenges = get_challenges(os.path.dirname(os.path.dirname(challenge_path)))
    assert challenges is not None

    return challenges.index(os.path.basename(challenge_path))


def copy_context(
    context: WrapContext, overrides: typing.Mapping[str, typing.Any]
) -> WrapContext:
    fields = {}
    for field in dataclasses.fields(context.__class__):
        fields[field.name] = getattr(context, field.name)

    for key, value in overrides.items():
        fields[key] = value

    return context.__class__(**fields)


def cli_challenge(
    context: WrapContext,
    callback: typing.Callable[[Track, WrapContext], typing.Sequence[LibError]],
    errors: typing.List[LibError],
) -> bool:
    json_path = os.path.join(context.challenge_path, "challenge.json")
    if not os.path.isfile(json_path):
        errors.append(BuildError(context="challenge.json", msg="is not a file"))
        return False

    try:
        with open(json_path) as h:
            raw_track = json.load(h)
    except Exception as e:
        errors.append(
            BuildError(context="challenge.json", msg="is not valid JSON", error=e)
        )
        return False

    track, parse_errors = parse_track(raw_track)
    if track is None or parse_errors:
        errors += parse_errors
        return False

    if context.skip_inactive and not track.active:
        errors.append(SkipError())
        return False

    errors += callback(track, context)

    return not errors


def cli_challenge_wrapper(
    root_directory: str,
    challenges: typing.Optional[typing.Sequence[str]],
    context: WC,
    callback: typing.Callable[[Track, WC], typing.Sequence[LibError]],
    console: typing.Optional[rich.console.Console] = None,
) -> bool:
    if not challenges:
        next_challenges = get_challenges(root_directory)
        if next_challenges is None:
            print_errors(
                console=console,
                errors=[
                    BuildError(
                        context="Respository",
                        msg="does not contain a challenges folder",
                    )
                ],
            )
            if console:
                console.print()

            return False

        challenges = next_challenges

    skip_inactive = True if len(challenges) <= 1 else False

    error_map: typing.Dict[str, typing.List[LibError]] = {}
    threads: typing.List[typing.Tuple[threading.Thread, str]] = []
    for challenge in challenges:
        errors: typing.List[LibError] = []
        error_map[challenge] = errors

        challenge_path = os.path.join(root_directory, "challenges", challenge)
        challenge_context = copy_context(
            context, {"challenge_path": challenge_path, "skip_inactive": skip_inactive}
        )

        threads.append(
            (
                threading.Thread(
                    target=cli_challenge,
                    kwargs={
                        "context": challenge_context,
                        "callback": callback,
                        "errors": errors,
                    },
                ),
                challenge,
            )
        )

    for thread, _ in threads:
        thread.start()

    all_errors = []

    with rich.progress.Progress(
        rich.progress.TextColumn("{task.description}"),
        rich.progress.TimeElapsedColumn(),
        rich.progress.SpinnerColumn(style="progress.elapsed"),
        console=console,
    ) as progress:
        challenge_tasks = {}
        for _, challenge in threads:
            task_id = progress.add_task(challenge)
            challenge_tasks[challenge] = progress.tasks[task_id]

        running_queue: typing.List[typing.Tuple[threading.Thread, str]] = [*threads]
        while running_queue:
            thread, challenge = running_queue.pop(0)

            if thread.is_alive():
                running_queue.append((thread, challenge))
                time.sleep(0.1)
                continue

            errors = error_map[challenge]
            all_errors += errors

            print_errors(
                console=console,
                prefix=context.error_prefix + [challenge],
                errors=errors,
                elapsed_time=challenge_tasks[challenge].elapsed,
            )
            progress.remove_task(challenge_tasks[challenge].id)

    return get_exit_status(all_errors)
