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
from ..error import DeployError, SkipError, LibError, print_errors
from ..schema import Track

from .common import (
    cli_challenge_wrapper,
    WrapContext,
    port_generator,
    get_create_network,
    get_challenge_index,
    CliContext,
)


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str]
    ip: typing.Sequence[str]
    network: typing.Sequence[str]
    port: int


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    network: docker.models.networks.Network
    host: str
    port: int
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


def start(track: Track, context: Context) -> typing.Sequence[LibError]:
    if not track.deploy:
        return [SkipError()]

    next_port = port_generator(
        context.port + get_challenge_index(context.challenge_path) * CHALLENGE_MAX_PORTS
    )

    errors: typing.List[LibError] = []
    for i, deployer in enumerate(track.deploy):
        errors += BuildDeployer.get(deployer).start(
            deployer=deployer,
            context=DeployContext(
                name=f"{track.tag or track.name}_{i}",
                path=context.challenge_path,
                docker_client=context.docker_client,
                network=context.network.name,
                host=context.host,
                port_generator=next_port,
            ),
        )

    return errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=challenges,
        help="Name of challenge",
        default=[],
    )
    parser.add_argument(
        "-i", "--ip", action="append", help="Host IPs to proxy with", default=[]
    )
    parser.add_argument(
        "-n", "--network", action="append", help="Name of network", default=[]
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Starting port for challenges",
        default=CHALLENGE_BASE_PORT,
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    arg_hosts = args.ip if args.ip else ["0.0.0.0"]
    arg_networks = args.network if args.network else [DEPLOY_NETWORK]

    if len(arg_networks) > len(arg_hosts):
        print_errors(
            prefix=[],
            errors=[DeployError(context="Networks", msg="do not have enough hosts")],
            console=cli_context.console,
        )
        return False

    is_ok = True
    for arg_host, arg_network in zip(arg_hosts, arg_networks):
        network = get_create_network(cli_context.docker_client, arg_network)
        if network is None:
            print_errors(
                prefix=[arg_network],
                errors=[DeployError(context=arg_network, msg="not started")],
                console=cli_context.console,
            )
            continue

        context = Context(
            challenge_path="",
            error_prefix=[network.name] if len(arg_networks) > 1 else [],
            skip_inactive=False,
            network=network,
            docker_client=cli_context.docker_client,
            host=arg_host,
            port=args.port,
        )

        if not cli_challenge_wrapper(
            root_directory=cli_context.root_directory,
            challenges=args.challenge,
            context=context,
            callback=start,
            console=cli_context.console,
        ):
            is_ok = False

    return is_ok
