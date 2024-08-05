import argparse
import os
import os.path

from .cmd import CLI, Command, Menu
from .logging import LOG, setup_logging

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
    root_directory = os.environ.get("TARGET") or "."

    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose", help="Verbose mode", action="store_true", default=False)

    build_menu(parser, CLI, root_directory)

    args = parser.parse_args()

    setup_logging(LOG, args.verbose)

    return 0 if run_menu(args, CLI, root_directory) else 1
