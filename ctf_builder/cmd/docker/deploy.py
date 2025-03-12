import argparse
import dataclasses
import typing

import docker
import docker.models.networks

from ...error import LibError, SkipError
from ...models.challenge import Track
from ...models.deploy.base import DockerDeployContext
from ..common import CliContext, WrapContext, cli_challenge_wrapper, get_challenges


@dataclasses.dataclass(frozen=True)
class Args:
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    repository: typing.Optional[str] = dataclasses.field(default=None)


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )
    repository: typing.Optional[str] = dataclasses.field(default=None)


def deploy(track: Track, context: Context) -> typing.Sequence[LibError]:
    if not track.deploy:
        return [SkipError()]

    errors: typing.List[LibError] = []
    for i, deployer in enumerate(track.deploy):
        errors += deployer.docker_deploy(
            DockerDeployContext(
                name=f"{track.tag or track.name}-{i}",
                root=context.challenge_path,
                docker_client=context.docker_client,
                network=None,
                repository=context.repository,
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
        "-r",
        "--repository",
        help="Container repository path for challenges",
        default=None,
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        docker_client=cli_context.docker_client,
        repository=args.repository,
    )

    return cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=deploy,
        console=cli_context.console,
    )
