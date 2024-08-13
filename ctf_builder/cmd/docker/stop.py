import argparse
import dataclasses
import typing

import docker
import docker.models.networks

from ...config import DEPLOY_NETWORK
from ...error import DeployError, LibError, SkipError, print_errors
from ...models.challenge import Track
from ...models.deploy.base import DockerDeployContext
from ..common import (
    CliContext,
    WrapContext,
    cli_challenge_wrapper,
    get_challenges,
    get_network,
)


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    network: typing.Sequence[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    network: docker.models.networks.Network
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


def stop(track: Track, context: Context) -> typing.Sequence[LibError]:
    if not track.deploy:
        return [SkipError()]

    errors: typing.List[LibError] = []
    for i, deployer in enumerate(track.deploy):
        errors += deployer.docker_stop(
            DockerDeployContext(
                name=f"{track.tag or track.name}-{i}",
                root=context.challenge_path,
                docker_client=context.docker_client,
                network=context.network.name,
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
        "-n", "--network", action="append", help="Name of network", default=[]
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    is_ok = True
    arg_networks = args.network if args.network else [DEPLOY_NETWORK]
    for arg_network in arg_networks:
        network = get_network(cli_context.docker_client, arg_network)
        if network is None:
            print_errors(
                prefix=[arg_network],
                errors=[DeployError(context=arg_network, msg="not found")],
                console=cli_context.console,
            )
            continue

        context = Context(
            challenge_path="",
            error_prefix=[network.name] if len(arg_networks) > 1 else [],
            skip_inactive=False,
            network=network,
            docker_client=cli_context.docker_client,
        )

        if not cli_challenge_wrapper(
            root_directory=cli_context.root_directory,
            challenges=args.challenge if args.challenge else None,
            context=context,
            callback=stop,
            console=cli_context.console,
        ):
            is_ok = False

    return is_ok
