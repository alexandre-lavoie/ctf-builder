import argparse
import os
import os.path
import time
import typing

import docker
import rich.console

from .cmd.cli import CLI, Command, Menu
from .cmd.common import CliContext


def build_command(
    subparser: argparse._SubParsersAction,  # type: ignore
    name: str,
    command: Command,
    root_directory: str,
) -> None:
    parser = subparser.add_parser(name=name, help=command.help)
    command.args(parser, root_directory)


def build_menu(
    parser: argparse.ArgumentParser, menu: Menu, root_directory: str, depth: int = 0
) -> None:
    subparser = parser.add_subparsers(dest=f"_{depth}", required=True)

    for option_name, option in menu.options.items():
        if isinstance(option, Command):
            build_command(subparser, option_name, option, root_directory)
        elif isinstance(option, Menu):
            build_menu(
                subparser.add_parser(name=option_name, help=option.help),
                option,
                root_directory,
                depth + 1,
            )


def run_menu(
    args: typing.Any, menu: Menu, cli_context: CliContext, depth: int = 0
) -> bool:
    target = getattr(args, f"_{depth}")

    option = menu.options.get(target)
    if isinstance(option, Command):
        return option.cli(args, cli_context)
    elif isinstance(option, Menu):
        return run_menu(args, option, cli_context, depth + 1)

    return False


def cli() -> int:
    root_directory = os.environ.get("CTF") or "."

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--quiet", action="store_true", help="Turn off logging", default=False
    )

    build_menu(parser, CLI, root_directory)

    args = parser.parse_args()

    docker_client = docker.from_env()
    console = rich.console.Console(quiet=args.quiet)

    cli_context = CliContext(
        root_directory=root_directory, console=console, docker_client=docker_client
    )

    path = []
    i = 0
    while True:
        try:
            path.append(getattr(args, f"_{i}"))
        except:
            break

        i += 1

    console.print(f"[bold blue]ctf-builder[/] - [yellow]{' '.join(path)}[/]\n")

    start = time.time()
    is_ok = run_menu(args, CLI, cli_context)
    end = time.time()

    delta = end - start
    delta_str = f"{delta:.2f}s"

    console.print()

    if is_ok:
        console.print(
            "[bold green]OK[/]", "in", f"[green]{delta_str}[/]", highlight=False
        )
    else:
        console.print(
            "[bold red]ERROR[/]", "in", f"[red]{delta_str}[/]", highlight=False
        )

    return 0 if is_ok else 1
