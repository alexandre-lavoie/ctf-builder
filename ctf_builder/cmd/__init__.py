import argparse
import dataclasses
import typing

from .build import cli as build_cli
from .build import cli_args as build_args

from .schema import cli as schema_cli
from .schema import cli_args as schema_args

from .ctfd.challenges import cli as ctfd_challenges_cli
from .ctfd.challenges import cli_args as ctfd_challenges_args

from .ctfd.setup import cli as ctfd_setup_cli
from .ctfd.setup import cli_args as ctfd_setup_args

from .ctfd.teams import cli as ctfd_teams_cli
from .ctfd.teams import cli_args as ctfd_teams_args

@dataclasses.dataclass
class Command:
    args: typing.Callable[[argparse.ArgumentParser, str], None]
    cli: typing.Callable[[typing.Any, str], bool]
    help: typing.Optional[str] = dataclasses.field(default=None)

@dataclasses.dataclass
class Menu:
    options: typing.Mapping[str, typing.Union[Command, "Menu"]] = dataclasses.field(default_factory=dict)
    help: typing.Optional[str] = dataclasses.field(default=None)

CLI = Menu(
    help="Main",
    options={
        "build": Command(
            help="Build challenge static files",
            args=build_args,
            cli=build_cli
        ),
        "schema": Command(
            help="Build schemas for internal types",
            args=schema_args,
            cli=schema_cli
        ),
        "ctfd": Menu(
            help="Tools for CTFd",
            options={
                "init": Command(
                    help="Setup CTFd",
                    args=ctfd_setup_args,
                    cli=ctfd_setup_cli
                ),
                "deploy": Menu(
                    help="Deploy to CTFd",
                    options={
                        "challenges": Command(
                            help="Deploy challenges to CTFd",
                            args=ctfd_challenges_args,
                            cli=ctfd_challenges_cli
                        ),
                        "teams": Command(
                            help="Deploy teams to CTFd",
                            args=ctfd_teams_args,
                            cli=ctfd_teams_cli
                        )
                    }
                )
            }
        )
    }
)
