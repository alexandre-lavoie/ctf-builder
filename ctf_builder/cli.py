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
    commands: typing.Mapping[str, Command] = dataclasses.field(default_factory=dict)
    menus: typing.Mapping[str, "Menu"] = dataclasses.field(default_factory=dict)
    help: typing.Optional[str] = dataclasses.field(default=None)

CLI = Menu(
    help="Main menu",
    commands={
        "build": Command(
            help="Build challenge static files",
            args=build_args,
            cli=build_cli
        ),
        "schema": Command(
            help="Build schemas for internal types",
            args=schema_args,
            cli=schema_cli
        )
    },
    menus={
        "ctfd": Menu(
            help="Tools for CTFd",
            commands={
                "challenges": Command(
                    help="Deploy challenges to CTFd",
                    args=ctfd_challenges_args,
                    cli=ctfd_challenges_cli
                ),
                "setup": Command(
                    help="Setup CTFd",
                    args=ctfd_setup_args,
                    cli=ctfd_setup_cli
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

def build_command(subparser: argparse._SubParsersAction, name: str, command: Command, root_directory: str):
    parser = subparser.add_parser(name=name, help=command.help)
    command.args(parser, root_directory)

def build_menu(parser: argparse.ArgumentParser, menu: Menu, root_directory: str, depth: int=0):
    subparser = parser.add_subparsers(dest=f"_{depth}", required=True)

    for command_name, command in menu.commands.items():
        build_command(subparser, command_name, command, root_directory)

    for menu_name, menu in menu.menus.items():
        build_menu(subparser.add_parser(name=menu_name, help=menu.help), menu, root_directory, depth + 1)

def run_menu(args, menu: Menu, root_directory: str, depth: int=0) -> bool:
    target = getattr(args, f"_{depth}")

    command = menu.commands.get(target)
    if command:
        return command.cli(args, root_directory)

    sub_menu = menu.menus.get(target)
    if sub_menu:
        return run_menu(args, sub_menu, root_directory, depth + 1)

    return False

def cli() -> int:
    root_directory = os.environ.get("CTF") or "."

    parser = argparse.ArgumentParser()
    build_menu(parser, CLI, root_directory)

    args = parser.parse_args()

    return 0 if run_menu(args, CLI, root_directory) else 1
