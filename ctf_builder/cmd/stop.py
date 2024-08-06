import argparse
import dataclasses
import glob
import os.path
import typing

import docker
import docker.models.networks

from ..build import DeployContext, BuildDeployer
from ..config import DEPLOY_NETWORK
from ..error import DeployError, SkipError, LibError, print_errors
from ..schema import Track

from .common import WrapContext, get_network, cli_challenge_wrapper, CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str]
    network: typing.Sequence[str]


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
        errors += BuildDeployer.get(deployer).stop(
            deployer=deployer,
            context=DeployContext(
                name=f"{track.tag or track.name}_{i}",
                path=context.challenge_path,
                docker_client=context.docker_client,
                network=context.network.name,
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
            challenges=args.challenge,
            context=context,
            callback=stop,
            console=cli_context.console,
        ):
            is_ok = False

    return is_ok
