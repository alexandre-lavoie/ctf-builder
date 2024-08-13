import argparse
import dataclasses
import typing

import docker
import docker.models.networks

from ...config import (
    CHALLENGE_BASE_PORT,
    CHALLENGE_MAX_PORTS,
    DEPLOY_NETWORK,
    NULL_VALUES,
)
from ...error import DeployError, LibError, SkipError, print_errors
from ...models.challenge import Track
from ...models.deploy.base import DockerDeployContext
from ..common import (
    CliContext,
    WrapContext,
    cli_challenge_wrapper,
    get_challenge_index,
    get_challenges,
    get_create_network,
    port_generator,
)


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    ip: typing.Sequence[typing.Optional[str]] = dataclasses.field(default_factory=list)
    network: typing.Sequence[str] = dataclasses.field(default_factory=list)
    port: int = dataclasses.field(default=CHALLENGE_BASE_PORT)
    detach: bool = dataclasses.field(default=False)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    network: docker.models.networks.Network
    port: int
    host: typing.Optional[str] = dataclasses.field(default=None)
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
        errors += deployer.docker_start(
            DockerDeployContext(
                name=f"{track.tag or track.name}-{i}",
                root=context.challenge_path,
                docker_client=context.docker_client,
                network=context.network.name,
                host=context.host,
                port_generator=next_port,
            ),
        )

    return errors


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
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
    parser.add_argument(
        "-d",
        "--detach",
        action="store_true",
        help="Do not attach ports to hosts",
        default=False,
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

    arg_optional_hosts: typing.Sequence[typing.Optional[str]] = [
        host if host not in NULL_VALUES else None for host in arg_hosts
    ]

    is_ok = True
    for arg_host, arg_network in zip(arg_optional_hosts, arg_networks):
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
            challenges=args.challenge if args.challenge else None,
            context=context,
            callback=start,
            console=cli_context.console,
        ):
            is_ok = False

    return is_ok
