import argparse
import dataclasses
import time
import typing

import docker

from ..config import DEPLOY_ATTEMPTS, DEPLOY_SLEEP
from ..docker import to_docker_tag
from ..error import DeployError, LibError
from ..models.challenge import Track
from ..models.deploy import Deploy
from ..models.deploy.base import DockerDeployContext
from ..models.test.base import TestContext
from .common import (
    CliContext,
    WrapContext,
    cli_challenge_wrapper,
    create_network,
    get_challenges,
)


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
                to_docker_tag(f"ctf-builder_test-{track.tag or track.name}"),
            )
        ) is None:
            return [DeployError(context="Network", msg="failed to start")]
    else:
        network = None

    errors: typing.List[LibError] = []
    running_deployers: typing.List[typing.Tuple[Deploy, DockerDeployContext]] = []
    try:
        waiting_deployers: typing.List[typing.Tuple[Deploy, DockerDeployContext]] = []
        if network:
            for i, deployer in enumerate(track.deploy):
                deployer_context = DockerDeployContext(
                    name=f"{track.tag or track.name}-{i}",
                    root=context.challenge_path,
                    docker_client=context.docker_client,
                    network=network.name,
                    host=None,
                    tag=False,
                )

                deployer_errors = deployer.docker_start(
                    context=deployer_context, skip_reuse=False
                )
                errors += deployer_errors

                if not deployer_errors:
                    running_deployers.append((deployer, deployer_context))

                    if deployer.has_healthcheck():
                        waiting_deployers.append((deployer, deployer_context))

        if errors:
            return errors

        for i in range(DEPLOY_ATTEMPTS):
            waiting_deployers_next: typing.List[
                typing.Tuple[Deploy, DockerDeployContext]
            ] = []

            for deployer, deployer_context in waiting_deployers:
                if deployer.docker_healthcheck(context=deployer_context):
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

        for test in track.test:
            errors += test.build(
                TestContext(
                    name=f"{track.tag or track.name}",
                    root=context.challenge_path,
                    network=network.name if network else None,
                    challenges=track.challenges,
                    deployers=track.deploy,
                    docker_client=context.docker_client,
                ),
            )
    finally:
        for deployer, deployer_context in running_deployers:
            try:
                errors += deployer.docker_stop(
                    context=deployer_context, skip_not_found=False
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
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
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
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=test,
        console=cli_context.console,
    )
