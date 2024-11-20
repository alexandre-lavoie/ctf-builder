import argparse
import dataclasses
import json
import os
import os.path
import threading
import time
import typing

import docker
import docker.errors
import docker.models.networks
import rich.console
import rich.control
import rich.progress

from ..config import CHALLENGE_MAX_PORTS
from ..error import BuildError, LibError, SkipError, get_exit_status, print_errors
from ..models.challenge import Track


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


class ArgumentError(Exception):
    pass


class ExitError(Exception):
    pass


class ErrorArgumentParser(argparse.ArgumentParser):
    def error(self, message: typing.Optional[str] = None) -> None:  # type: ignore
        raise ArgumentError(message)

    def exit(self, status: int = 0, message: typing.Optional[str] = None) -> None:  # type: ignore
        raise ExitError(message)


def port_generator(port: int) -> typing.Generator[typing.Optional[int], None, None]:
    max_port = min(port + CHALLENGE_MAX_PORTS, MAX_TCP_PORT)
    while True:
        if port < 0 or port > max_port:
            break

        yield port

        port += 1

    while True:
        yield None


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

    challenges = []
    for _, directories, _ in os.walk(challenge_directory):
        for directory in directories:
            challenges.append(directory)

        break

    challenges = sorted(challenges)

    return challenges


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

    track, parse_errors = Track.parse(raw_track)
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
    skip_inactive = challenges is None

    if challenges is None:
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

            return False

        challenges = next_challenges

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

    if console:
        console.control(rich.control.Control.move(0, -1))

    return get_exit_status(all_errors)
