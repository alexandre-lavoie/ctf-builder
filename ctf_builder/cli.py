import argparse
import dataclasses
import os
import os.path
import typing

from .tools.build import cli as build_cli
from .tools.build import cli_args as build_args

from .tools.schema import cli as schema_cli
from .tools.schema import cli_args as schema_args

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
    help="Main menu",
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

def build_command(subparser: argparse._SubParsersAction, name: str, command: Command, root_directory: str):
    parser = subparser.add_parser(name=name, help=command.help)
    command.args(parser, root_directory)

def build_menu(parser: argparse.ArgumentParser, menu: Menu, root_directory: str, depth: int=0):
    subparser = parser.add_subparsers(dest=f"_{depth}", required=True)

    for option_name, option in menu.options.items():
        if isinstance(option, Command):
            build_command(subparser, option_name, option, root_directory)
        elif isinstance(option, Menu):
            build_menu(subparser.add_parser(name=option_name, help=option.help), option, root_directory, depth + 1)

def run_menu(args, menu: Menu, root_directory: str, depth: int=0) -> bool:
    target = getattr(args, f"_{depth}")

    option = menu.options.get(target)
    if isinstance(option, Command):
        return option.cli(args, root_directory)
    elif isinstance(option, Menu):
        return run_menu(args, option, root_directory, depth + 1)

    return False

def cli() -> int:
    root_directory = os.environ.get("CTF") or "."

    parser = argparse.ArgumentParser()
    build_menu(parser, CLI, root_directory)

    args = parser.parse_args()

    return 0 if run_menu(args, CLI, root_directory) else 1
