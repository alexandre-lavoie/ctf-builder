import argparse
import dataclasses
import glob
import os
import os.path
import time
import typing

import docker

from ..build.deployer import BuildDeployer, DeployContext
from ..build.tester import BuildTester, TestContext
from ..build.utils import to_docker_tag
from ..config import DEPLOY_ATTEMPTS, DEPLOY_SLEEP
from ..error import DeployError, LibError
from ..schema import Deployer, Track
from .common import CliContext, WrapContext, cli_challenge_wrapper, create_network


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient]


def test(track: Track, context: Context) -> typing.Sequence[LibError]:
    if context.docker_client is not None:
        if (
            network := create_network(
                context.docker_client,
                to_docker_tag(f"ctf-builder_test_{track.tag or track.name}"),
            )
        ) is None:
            return [DeployError(context="Network", msg="failed to start")]
    else:
        network = None

    errors: typing.List[LibError] = []
    running_deployers: typing.List[typing.Tuple[Deployer, DeployContext]] = []
    try:
        waiting_deployers: typing.List[typing.Tuple[Deployer, DeployContext]] = []
        if network:
            for i, deployer in enumerate(track.deploy):
                deployer_context = DeployContext(
                    name=f"host_{i}",
                    path=context.challenge_path,
                    docker_client=context.docker_client,
                    network=network.name,
                    host=None,
                )

                builder = BuildDeployer.get(deployer)

                deployer_errors = builder.start(
                    deployer=deployer, context=deployer_context, skip_reuse=False
                )
                errors += deployer_errors

                if not deployer_errors:
                    running_deployers.append((deployer, deployer_context))

                    if builder.has_healthcheck(
                        deployer=deployer, context=deployer_context
                    ):
                        waiting_deployers.append((deployer, deployer_context))

        if errors:
            return errors

        for i in range(DEPLOY_ATTEMPTS):
            waiting_deployers_next: typing.List[
                typing.Tuple[Deployer, DeployContext]
            ] = []

            for deployer, deployer_context in waiting_deployers:
                if BuildDeployer.get(deployer).is_healthy(
                    deployer=deployer, context=deployer_context
                ):
                    continue

                waiting_deployers_next.append((deployer, deployer_context))

            if not waiting_deployers_next:
                break

            waiting_deployers = waiting_deployers_next

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


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
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


def cli(args: Args, cli_context: CliContext) -> bool:
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
