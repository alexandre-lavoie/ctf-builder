import dataclasses
import glob
import json
import os.path
import typing

import docker
import docker.errors
import docker.models.networks

from ..config import CHALLENGE_MAX_PORTS
from ..error import ParseError, LibError, SkipError, print_errors, get_exit_status
from ..parse import parse_track
from ..schema import Track


def host_generator(
    ips: typing.Sequence[str],
) -> typing.Generator[typing.Optional[str], None, None]:
    for ip in ips:
        yield ip

    while True:
        yield None


def port_generator(port: int) -> typing.Generator[typing.Optional[int], None, None]:
    for next_port in range(port, port + CHALLENGE_MAX_PORTS):
        yield next_port

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


def get_create_network(
    client: docker.DockerClient, name: typing.Optional[str] = None
) -> typing.Optional[docker.models.networks.Network]:
    network = get_network(client, name)
    if network is not None:
        return network

    try:
        return client.networks.create(name, driver="bridge")
    except docker.errors.APIError:
        pass

    return None


@dataclasses.dataclass
class WrapContext:
    challenge_path: str
    error_prefix: str


def get_challenges(root_directory: str) -> typing.Sequence[str]:
    if not os.path.isdir(root_directory):
        return []

    out = []
    for file in glob.glob("**/challenge.json", root_dir=root_directory, recursive=True):
        path = os.path.join(root_directory, file)
        name = os.path.basename(os.path.dirname(path))
        out.append(name)

    return out


def get_challenge_index(challenge_path: str) -> int:
    challenges = get_challenges(os.path.basename(os.path.basename(challenge_path)))
    return challenges.index(os.path.basename(challenge_path))


def cli_challenge_wrapper(
    root_directory: str,
    challenges: typing.Sequence[str],
    context: WrapContext,
    callback: typing.Callable[[Track, WrapContext], typing.Sequence[LibError]],
) -> bool:
    if not challenges:
        challenges = get_challenges(root_directory)

    skip_inactive = True if len(challenges) <= 1 else False

    error_map: typing.Dict[str, typing.List[LibError]] = {}
    for challenge in challenges:
        errors = []
        error_map[challenge] = errors

        challenge_path = os.path.join(root_directory, "challenges", challenge)
        json_path = os.path.join(challenge_path, "challenge.json")
        if not os.path.isfile(json_path):
            errors.append(ParseError("challenge.json not found"))
            continue

        try:
            with open(json_path) as h:
                raw_track = json.load(h)
        except:
            errors.append(ParseError("invalid JSON"))
            continue

        track, parse_errors = parse_track(raw_track)
        if parse_errors:
            errors += parse_errors
            continue

        if skip_inactive and not track.active:
            errors.append(SkipError())
            continue

        context.challenge_path = challenge_path

        errors += callback(track, context)

    all_errors = []
    for challenge, errors in error_map.items():
        all_errors += errors

        print_errors(context.error_prefix + challenge, errors)

    return get_exit_status(all_errors)
