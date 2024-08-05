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
from ..error import LibError, TestError
from ..schema import Track

from .common import cli_challenge_wrapper, WrapContext, get_create_network


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient]


def test(track: Track, context: Context) -> typing.Sequence[LibError]:
    network_name = to_docker_tag(f"ctf-builder_{track.name}_test")
    if context.docker_client:
        network = get_create_network(context.docker_client, network_name)
    else:
        network = None

    errors = []
    running_deployers = []
    try:
        if network:
            for i, deployer in enumerate(track.deploy):
                deployer_context = DeployContext(
                    name=f"{network_name}_{i}",
                    path=context.challenge_path,
                    docker_client=context.docker_client,
                    network=network.id,
                    host=None,
                )

                deployer_errors = BuildDeployer.get(deployer).start(
                    deployer=deployer, context=deployer_context
                )
                errors += deployer_errors

                if not deployer_errors:
                    running_deployers.append((deployer, deployer_context))

        for i in range(DEPLOY_ATTEMPTS):
            is_ok = True
            for deployer, deployer_context in running_deployers:
                if not BuildDeployer.get(deployer).is_active(
                    deployer=deployer, context=deployer_context
                ):
                    is_ok = False

            if is_ok:
                break

            time.sleep(DEPLOY_SLEEP)
        else:
            return errors + [TestError("deployment did not start")]

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
                BuildDeployer.get(deployer).stop(
                    deployer=deployer, context=deployer_context
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


def cli(args, root_directory: str) -> bool:
    context = Context(
        challenge_path="",
        error_prefix="",
        skip_inactive=False,
        docker_client=docker.from_env(),
    )

    return cli_challenge_wrapper(
        root_directory=root_directory,
        challenges=args.challenge,
        context=context,
        callback=test,
    )
