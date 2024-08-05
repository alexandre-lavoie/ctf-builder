import argparse
import dataclasses
import glob
import os
import os.path
import typing

import docker
import docker.models.networks

from ..build import DeployContext, BuildDeployer
from ..config import CHALLENGE_MAX_PORTS, CHALLENGE_BASE_PORT, DEPLOY_NETWORK
from ..error import DeployError, LibError, print_errors
from ..schema import Track

from .common import cli_challenge_wrapper, WrapContext, host_generator, port_generator, get_create_network, get_challenge_index

@dataclasses.dataclass
class Context(WrapContext):
    network: docker.models.networks.Network
    port: int
    host_generator: typing.Generator[typing.Optional[str], None, None]
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(default=None)

def start(track: Track, context: Context) -> typing.Sequence[LibError]:
    next_port = port_generator(context.port + get_challenge_index(context.challenge_path) * CHALLENGE_MAX_PORTS)

    host = None
    errors = []
    for i, deployer in enumerate(track.deploy):
        build = BuildDeployer.get(deployer)

        if build.has_host(deployer) and not host:
            if (host := next(context.host_generator)) is None:
                errors.append(DeployError("no more host ip"))
                continue

        errors += build.start(
            deployer=deployer,
            context=DeployContext(
                name=f"{context.network.name}_{track.name}_{i}",
                path=context.challenge_path,
                docker_client=context.docker_client,
                network=context.network.name,
                host=host,
                port_generator=next_port
            )
        )

    return errors

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-c", "--challenge", action="append", choices=challenges, help="Name of challenge", default=[])
    parser.add_argument("-i", "--ip", action="append", help="Host IPs to proxy with", default=[])
    parser.add_argument("-n", "--network", action="append", help="Name of network", default=[])
    parser.add_argument("-p", "--port", type=int, help="Starting port for challenges", default=CHALLENGE_BASE_PORT)

def cli(args, root_directory: str) -> bool:
    docker_client = docker.from_env()

    next_host = host_generator(args.ip if args.ip else ["0.0.0.0"])

    is_ok = True
    arg_networks = args.network if args.network else [DEPLOY_NETWORK]
    for arg_network in arg_networks:
        network = get_create_network(docker_client, arg_network)
        if network is None:
            print_errors(arg_network, [DeployError("not started")])
            continue

        context = Context(
            challenge_path="",
            error_prefix=f"{network.name} > " if len(arg_networks) > 1 else "",
            network=network,
            docker_client=docker_client,
            host_generator=next_host,
            port=args.port
        )

        if not cli_challenge_wrapper(
            root_directory=root_directory,
            challenges=args.challenge,
            context=context,
            callback=start
        ):
            is_ok = False

    return is_ok
