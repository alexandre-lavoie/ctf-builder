import argparse
import dataclasses
import typing

from .build import cli as build_cli, cli_args as build_args
from .documentation import cli as documentation_cli, cli_args as documentation_args
from .start import cli as start_cli, cli_args as start_args
from .stop import cli as stop_cli, cli_args as stop_args
from .schema import cli as schema_cli, cli_args as schema_args
from .test import cli as test_cli, cli_args as test_args
from .ctfd.challenges import (
    cli as ctfd_challenges_cli,
    cli_args as ctfd_challenges_args,
)
from .ctfd.setup import cli as ctfd_setup_cli, cli_args as ctfd_setup_args
from .ctfd.teams import cli as ctfd_teams_cli, cli_args as ctfd_teams_args

from .common import CliContext


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
        "start": Command(help="Start challenges", args=start_args, cli=start_cli),
        "stop": Command(help="Stop challenges", args=stop_args, cli=stop_cli),
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
    },
)
