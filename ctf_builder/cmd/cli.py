import argparse
import dataclasses
import typing

from .build import cli as build_cli
from .build import cli_args as build_args
from .common import CliContext
from .ctfd.challenges import cli as ctfd_challenges_cli
from .ctfd.challenges import cli_args as ctfd_challenges_args
from .ctfd.dev import cli as ctfd_dev_cli
from .ctfd.dev import cli_args as ctfd_dev_args
from .ctfd.setup import cli as ctfd_setup_cli
from .ctfd.setup import cli_args as ctfd_setup_args
from .ctfd.teams import cli as ctfd_teams_cli
from .ctfd.teams import cli_args as ctfd_teams_args
from .docker.deploy import cli as docker_deploy_cli
from .docker.deploy import cli_args as docker_deploy_args
from .docker.list import cli as docker_list_cli
from .docker.list import cli_args as docker_list_args
from .docker.start import cli as docker_start_cli
from .docker.start import cli_args as docker_start_args
from .docker.stop import cli as docker_stop_cli
from .docker.stop import cli_args as docker_stop_args
from .documentation import cli as documentation_cli
from .documentation import cli_args as documentation_args
from .k8s.build import cli as k8s_build_cli
from .k8s.build import cli_args as k8s_build_args
from .schema import cli as schema_cli
from .schema import cli_args as schema_args
from .test import cli as test_cli
from .test import cli_args as test_args


@dataclasses.dataclass
class Command:
    args: typing.Callable[[argparse.ArgumentParser, str], None]
    cli: typing.Callable[[typing.Any, CliContext], bool]
    help: typing.Optional[str] = dataclasses.field(default=None)


@dataclasses.dataclass
class Menu:
    options: typing.Mapping[str, typing.Union[Command, "Menu"]] = dataclasses.field(
        default_factory=dict
    )
    help: typing.Optional[str] = dataclasses.field(default=None)


CLI = Menu(
    help="Main",
    options={
        "build": Command(help="Build static files", args=build_args, cli=build_cli),
        "doc": Command(
            help="Build JSON schemas", args=documentation_args, cli=documentation_cli
        ),
        "schema": Command(
            help="Validate challenge.json", args=schema_args, cli=schema_cli
        ),
        "test": Command(help="Test challenges", args=test_args, cli=test_cli),
        "ctfd": Menu(
            help="CTFd integration",
            options={
                "init": Command(
                    help="Setup CTFd", args=ctfd_setup_args, cli=ctfd_setup_cli
                ),
                "dev": Command(
                    help="Run a CTFd development instance",
                    args=ctfd_dev_args,
                    cli=ctfd_dev_cli,
                ),
                "deploy": Menu(
                    help="Deploy to CTFd",
                    options={
                        "challenges": Command(
                            help="Deploy challenges to CTFd",
                            args=ctfd_challenges_args,
                            cli=ctfd_challenges_cli,
                        ),
                        "teams": Command(
                            help="Deploy teams to CTFd",
                            args=ctfd_teams_args,
                            cli=ctfd_teams_cli,
                        ),
                    },
                ),
            },
        ),
        "docker": Menu(
            help="Docker integration",
            options={
                "list": Command(
                    help="List container tags",
                    args=docker_list_args,
                    cli=docker_list_cli,
                ),
                "start": Command(
                    help="Start challenges",
                    args=docker_start_args,
                    cli=docker_start_cli,
                ),
                "stop": Command(
                    help="Stop challenges", args=docker_stop_args, cli=docker_stop_cli
                ),
                "deploy": Command(
                    help="Deploy challenge images",
                    args=docker_deploy_args,
                    cli=docker_deploy_cli,
                ),
            },
        ),
        "k8s": Menu(
            help="Kubernetes integration",
            options={
                "build": Command(
                    help="Build infrastructure files",
                    args=k8s_build_args,
                    cli=k8s_build_cli,
                ),
            },
        ),
    },
)
