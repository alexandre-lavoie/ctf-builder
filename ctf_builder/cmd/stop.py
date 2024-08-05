import argparse
import dataclasses
import glob
import os.path
import typing

import docker
import docker.models.networks

from ..build import DeployContext, BuildDeployer
from ..config import DEPLOY_NETWORK
from ..error import DeployError, LibError, print_errors
from ..schema import Track

from .common import WrapContext, get_network, cli_challenge_wrapper

@dataclasses.dataclass
class Context(WrapContext):
    network: docker.models.networks.Network
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(default=None)

def stop(track: Track, context: Context) -> typing.Sequence[LibError]:
    errors = []
    for i, deployer in enumerate(track.deploy):
        errors += BuildDeployer.get(deployer).stop(
            deployer=deployer,
            context=DeployContext(
                name=f"{context.network.name}_{track.name}_{i}",
                path=context.challenge_path,
                docker_client=context.docker_client,
                network=context.network.name
            )
        )

    return errors

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-c", "--challenge", action="append", choices=challenges, help="Name of challenge", default=[])
    parser.add_argument("-n", "--network", action="append", help="Name of network", default=[])

def cli(args, root_directory: str) -> bool:
    docker_client = docker.from_env()

    is_ok = True
    arg_networks = args.network if args.network else [DEPLOY_NETWORK]
    for arg_network in arg_networks:
        network = get_network(docker_client, arg_network)
        if network is None:
            print_errors(arg_network, [DeployError("not found")])
            continue

        context = Context(
            challenge_path="",
            error_prefix=f"{network.name} > " if len(arg_networks) > 1 else "",
            network=network,
            docker_client=docker_client
        )

        if not cli_challenge_wrapper(
            root_directory=root_directory,
            challenges=[args.challenge] if args.challenge else None,
            context=context,
            callback=stop
        ):
            is_ok = False

    return is_ok
