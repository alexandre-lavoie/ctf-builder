import argparse
import dataclasses
import json
import os.path
import tempfile
import time
import typing

import docker
import docker.models.containers
import rich.console
import rich.markup
import rich.progress

from ...config import CHALLENGE_BASE_PORT
from ...ctfd import ctfd_container, generate_key
from ...error import DeployError, LibError, get_exit_status, print_errors
from ..common import (
    ArgumentError,
    CliContext,
    ErrorArgumentParser,
    ExitError,
    get_challenges,
)
from .challenges import Args as ChallengesArgs
from .challenges import cli as challenges_cli
from .setup import Args as SetupArgs
from .setup import SetupData
from .setup import cli as setup_cli


@dataclasses.dataclass
class Args:
    port: int
    exit: bool = dataclasses.field(default=False)
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    base_port: int = dataclasses.field(default=CHALLENGE_BASE_PORT)


DEV_SETUP = SetupData(
    ctf_name="ctf-builder",
    ctf_description="Development environment for ctf-builder",
    user_mode="users",
    challenge_visibility="public",
    score_visibility="admins",
    account_visibility="admins",
    registration_visibility="public",
    verify_emails=False,
)

DEV_NAME = "admin"
DEV_PASSWORD = "admin"
DEV_EMAIL = "admin@ctfd.io"


def dev(args: Args, cli_context: CliContext) -> typing.Sequence[LibError]:
    container: typing.Optional[docker.models.containers.Container] = None

    ctfd_url = f"http://localhost:{args.port}"

    try:
        with rich.progress.Progress(
            rich.progress.TextColumn("{task.description}"),
            rich.progress.BarColumn(),
            rich.progress.TimeElapsedColumn(),
            rich.progress.MofNCompleteColumn(),
            console=cli_context.console,
        ) as progress:
            task_id = progress.add_task("Loading", total=4)

            # Start container
            start_time = time.time()
            container, container_errors = ctfd_container(
                name="ctf-builder_ctfd",
                docker_client=cli_context.docker_client,
                port=args.port,
            )
            end_time = time.time()

            print_errors(
                prefix=["container"],
                errors=container_errors,
                console=cli_context.console,
                elapsed_time=end_time - start_time,
            )
            if container == None or container_errors:
                return container_errors
            progress.update(task_id, advance=1)

            # Setup CTFd
            with tempfile.TemporaryDirectory() as temp_dir:
                setup_path = os.path.join(temp_dir, "setup.json")
                with open(setup_path, "w") as h:
                    json.dump(dataclasses.asdict(DEV_SETUP), h)

                setup_status = setup_cli(
                    cli_context=cli_context,
                    args=SetupArgs(
                        url=ctfd_url,
                        name=DEV_NAME,
                        email=DEV_EMAIL,
                        password=DEV_PASSWORD,
                        file=setup_path,
                    ),
                )

            if not setup_status:
                return [DeployError(context="setup", msg="failed to deploy")]
            progress.update(task_id, advance=1)

            # Generate API Key
            start_time = time.time()
            token = generate_key(url=ctfd_url, name=DEV_NAME, password=DEV_PASSWORD)
            end_time = time.time()

            token_errors = (
                [DeployError(context="token", msg="failed to get")]
                if token is None
                else []
            )
            print_errors(
                prefix=["token"],
                errors=token_errors,
                console=cli_context.console,
                elapsed_time=end_time - start_time,
            )
            if token is None:
                return token_errors
            progress.update(task_id, advance=1)

            _, api_key = token

            # Deploy challenges
            challenge_args = ChallengesArgs(
                api_key=api_key,
                url=ctfd_url,
                port=args.base_port,
                challenge=args.challenge,
            )

            challenge_status = challenges_cli(
                cli_context=cli_context,
                args=challenge_args,
            )
            if not challenge_status:
                return [DeployError(context="challenges", msg="failed to deploy")]
            progress.update(task_id, advance=1)

            # Progress cleanup
            progress.remove_task(task_id)

        if cli_context.console:
            cli_context.console.print("Running at", ctfd_url)

        # Check for interactive mode skips
        if args.exit or cli_context.console is None:
            return []

        # Parser for interactive mode
        parser = ErrorArgumentParser(prog="")

        parser.add_argument(
            "-r",
            "--reload",
            action="store_true",
            help="reload challenges",
            default=False,
        )

        parser.add_argument(
            "-e", "--exit", action="store_true", help="exit program", default=False
        )

        # Interactive mode
        while True:
            user_input = cli_context.console.input("\n> ").strip()
            user_args = user_input.split(" ")

            if "-e" not in user_args and "--exit" not in user_args:
                cli_context.console.print()

            try:
                interactive_args = parser.parse_args(user_args)
            except ArgumentError as e:
                cli_context.console.print(f"[red]{rich.markup.escape(str(e))}[/]")
                continue
            except ExitError as e:
                continue

            if interactive_args.exit:
                break

            if interactive_args.reload:
                challenges_cli(
                    cli_context=cli_context,
                    args=challenge_args,
                )

        return []
    except KeyboardInterrupt:
        return []
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except:
                pass


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument("-p", "--port", help="CTFd port", default=8000)
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
        default=[],
    )
    parser.add_argument(
        "-b",
        "--base_port",
        type=int,
        help="Starting port for challenges",
        default=CHALLENGE_BASE_PORT,
    )
    parser.add_argument("--exit", help="Exit instance when started", default=False)


def cli(args: Args, cli_context: CliContext) -> bool:
    errors = dev(args, cli_context)

    return get_exit_status(errors)
