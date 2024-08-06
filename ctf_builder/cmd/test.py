import argparse
import dataclasses
import glob
import os
import os.path
import time
import typing

import docker

from ..build import BuildTester, BuildDeployer, TestContext, DeployContext
from ..build.utils import to_docker_tag
from ..config import DEPLOY_SLEEP, DEPLOY_ATTEMPTS
from ..error import LibError, DeployError
from ..schema import Track

from .common import cli_challenge_wrapper, WrapContext, get_create_network, CliContext


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str]


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient]


def test(track: Track, context: Context) -> typing.Sequence[LibError]:
    network_name = to_docker_tag(f"ctf-builder_test_{track.tag or track.name}")
    if context.docker_client:
        network = get_create_network(context.docker_client, network_name)
    else:
        network = None

    errors: typing.List[LibError] = []
    running_deployers = []
    try:
        if network:
            for i, deployer in enumerate(track.deploy):
                deployer_context = DeployContext(
                    name=f"host_{i}",
                    path=context.challenge_path,
                    docker_client=context.docker_client,
                    network=network.name,
                    host=None,
                )

                deployer_errors = BuildDeployer.get(deployer).start(
                    deployer=deployer, context=deployer_context, skip_reuse=False
                )
                errors += deployer_errors

                if not deployer_errors:
                    running_deployers.append((deployer, deployer_context))

        for i in range(DEPLOY_ATTEMPTS):
            is_ok = True
            for deployer, deployer_context in running_deployers:
                if not BuildDeployer.get(deployer).is_healthy(
                    deployer=deployer, context=deployer_context
                ):
                    is_ok = False

            if is_ok:
                break

            time.sleep(DEPLOY_SLEEP)
        else:
            errors.append(
                DeployError(context="Deployments", msg="did not start successfully")
            )
            return errors

        for tester in track.test:
            errors += BuildTester.get(tester).build(
                tester=tester,
                context=TestContext(
                    path=context.challenge_path,
                    network=network.name if network else None,
                    challenges=track.challenges,
                    deployers=track.deploy,
                    docker_client=context.docker_client,
                ),
            )
    finally:
        for deployer, deployer_context in running_deployers:
            try:
                errors += BuildDeployer.get(deployer).stop(
                    deployer=deployer, context=deployer_context, skip_not_found=False
                )
            except:
                pass

        if network:
            try:
                network.remove()
            except:
                pass

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


def cli(args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        docker_client=cli_context.docker_client,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge,
        context=context,
        callback=test,
        console=cli_context.console,
    )
