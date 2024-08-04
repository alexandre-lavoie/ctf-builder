import argparse
import dataclasses
import glob
import json
import os
import os.path
import typing

import docker
import docker.errors
import docker.models.networks
import docker.types

from ..build import DeployContext, BuildDeployer
from ..config import CHALLENGE_MAX_PORTS, CHALLENGE_BASE_PORT
from ..error import DeployError, SkipError, LibError, print_errors, get_exit_status
from ..parse import parse_track

@dataclasses.dataclass
class CliContext:
    network: docker.models.networks.Network
    next_host: typing.Callable[[], typing.Optional[str]]
    port: int
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(default=None)

def start_challenge(json_path: str, skip_active: bool, cli_context: CliContext) -> typing.Sequence[typing.Union[LibError]]:
    if not os.path.exists(json_path):
        return [DeployError("file not found")]

    if not os.path.isfile(json_path):
        return [DeployError("not a file")]

    try:
        with open(json_path) as h:
            data = json.load(h)
    except:
        return [DeployError("invalid JSON")]

    track, errors = parse_track(data)
    if errors:
        return errors

    if not skip_active and not track.active:
        return [SkipError()]
    
    np = cli_context.port
    def next_port() -> typing.Optional[int]:
        nonlocal cli_context, np

        if np >= cli_context.port + CHALLENGE_MAX_PORTS:
            return None
        
        t = np
        np += 1

        return t
    
    host = None

    errors = []
    for i, deployer in enumerate(track.deploy):
        db = BuildDeployer.get(deployer)
        if db is None:
            errors.append(DeployError(f"unhandled {type(deployer)}"))
            continue

        if db.has_host(deployer) and not host:
            host = cli_context.next_host()

            if host is None:
                errors.append(DeployError("no more host ip"))
                continue

        deploy_context = DeployContext(
            name=f"{cli_context.network.name}_{track.name}_{i}",
            path=os.path.dirname(json_path),
            docker_client=cli_context.docker_client,
            network=cli_context.network.name,
            host=host,
            next_port=next_port
        )

        errors += db.start(deploy_context, deployer)

    return errors

def challenge_iter(root: str) -> typing.Sequence[str]:
    return glob.glob("**/challenge.json", root_dir=root, recursive=True)

def start_challenges(root: str, cli_context: CliContext) -> typing.Mapping[str, typing.Sequence[LibError]]:
    if not os.path.isdir(root):
        return {
            "": [DeployError("challenges directory not found")]
        }

    out = {}
    for file in challenge_iter(root):
        path = os.path.join(root, file)

        out[path] = start_challenge(path, skip_active=False, cli_context=cli_context)

        cli_context.port = cli_context.port + CHALLENGE_MAX_PORTS

    return out

def get_network(client: docker.DockerClient, name: typing.Optional[str] = None) -> docker.models.networks.Network:
    try:
        return client.networks.get(name)
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError:
        return None

    try:
        return client.networks.create(name, driver="bridge")
    except docker.errors.APIError:
        return None

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-c", "--challenge", choices=challenges, help="Name of challenge to start", default=None)
    parser.add_argument("-i", "--ip", action="append", help="Host IPs to proxy with", default=[])
    parser.add_argument("-n", "--network", action="append", help="Names of network to start", default=[])
    parser.add_argument("-p", "--port", type=int, help="Starting port for challenges", default=CHALLENGE_BASE_PORT)

def cli(args, root_directory: str) -> bool:
    challenge_directory = os.path.join(root_directory, "challenges")

    docker_client = docker.from_env()

    args_networks = args.network
    if not args_networks:
        args_networks.append("ctf-builder_deploy")

    args_hosts = args.ip
    if not args_hosts:
        args_hosts.append("0.0.0.0")
    host_index = 0

    def next_host() -> str:
        nonlocal host_index

        if host_index >= len(args_hosts):
            return None

        index = host_index
        host_index += 1
        return args_hosts[index]

    all_errors = []
    for arg_network in args_networks:
        network = get_network(docker_client, arg_network)
        if network is None:
            errors = [DeployError(f"network could not be started")]
            all_errors += errors
            print_errors(arg_network, errors)
            continue

        cli_context = CliContext(
            network=network,
            docker_client=docker_client,
            next_host=next_host,
            port=args.port
        )

        if args.challenge:
            path = os.path.join(challenge_directory, args.challenge, "challenge.json")

            for name in challenge_iter(challenge_directory):
                if args.challenge == os.path.basename(os.path.dirname(name)):
                    break

                cli_context.port += CHALLENGE_MAX_PORTS

            errors = start_challenge(
                path,
                skip_active=True,
                cli_context=cli_context
            )

            all_errors += errors

            if len(args_networks) > 1:
                prefix = network.name
            else:
                prefix = None

            print_errors(prefix, errors)
        else:
            for path, errors in start_challenges(
                challenge_directory,
                cli_context=cli_context
            ).items():
                all_errors += errors

                if len(args_networks) > 1:
                    prefix = f"{network.name} > {os.path.basename(os.path.dirname(path))}"
                else:
                    prefix = os.path.basename(os.path.dirname(path))

                print_errors(prefix, errors)

    return get_exit_status(all_errors)
