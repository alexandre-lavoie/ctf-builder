import argparse
import dataclasses
import os.path
import tempfile
import time
import typing

import docker
import docker.models.containers
import rich.console
import rich.control
import rich.markup
import rich.progress

from ...config import CHALLENGE_BASE_PORT, CHALLENGE_HOST
from ...ctfd.api import CTFdAPI
from ...ctfd.docker import ctfd_container
from ...ctfd.models import CTFdSetup, CTFdSetupUserMode, CTFdSetupVisibility
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
from .setup import cli as setup_cli


@dataclasses.dataclass
class Args:
    port: int
    hostname: str = dataclasses.field(default=CHALLENGE_HOST)
    exit: bool = dataclasses.field(default=False)
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    base_port: int = dataclasses.field(default=CHALLENGE_BASE_PORT)


DEV_SETUP = CTFdSetup(
    ctf_name="ctf-builder",
    ctf_description="Development environment for ctf-builder",
    user_mode=CTFdSetupUserMode.Users,
    challenge_visibility=CTFdSetupVisibility.Public,
    score_visibility=CTFdSetupVisibility.Admins,
    account_visibility=CTFdSetupVisibility.Admins,
    registration_visibility=CTFdSetupVisibility.Public,
    verify_emails=False,
)

DEV_NAME = "admin"
DEV_PASSWORD = "admin"
DEV_EMAIL = "admin@ctfd.io"


def dev(args: Args, cli_context: CliContext) -> typing.Sequence[LibError]:
    skip_ssl = True

    container: typing.Optional[docker.models.containers.Container] = None

    ctfd_url = f"http://{args.hostname}:{args.port}"

    try:
        with rich.progress.Progress(
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            console=cli_context.console,
        ) as progress:
            task_id = progress.add_task("container", total=1)

            # Start container
            container, container_errors = ctfd_container(
                name="ctf-builder_ctfd",
                docker_client=cli_context.docker_client,
                port=args.port,
            )

            elapsed = progress.tasks[task_id].elapsed
            progress.remove_task(task_id)

        if cli_context.console:
            cli_context.console.control(rich.control.Control.move(0, -1))

        print_errors(
            prefix=["container"],
            errors=container_errors,
            console=cli_context.console,
            elapsed_time=elapsed,
        )
        if container == None or container_errors:
            return container_errors

        # Setup CTFd
        with tempfile.TemporaryDirectory() as temp_dir:
            setup_path = os.path.join(temp_dir, "setup.json")
            with open(setup_path, "w") as h:
                h.write(DEV_SETUP.model_dump_json())

            setup_status = setup_cli(
                cli_context=cli_context,
                args=SetupArgs(
                    url=ctfd_url,
                    name=DEV_NAME,
                    email=DEV_EMAIL,
                    password=DEV_PASSWORD,
                    file=setup_path,
                    skip_ssl=skip_ssl,
                ),
            )

        if not setup_status:
            return [DeployError(context="setup", msg="failed to deploy")]

        # Generate API
        start_time = time.time()
        api = CTFdAPI.login(
            url=ctfd_url, name=DEV_NAME, password=DEV_PASSWORD, verify_ssl=not skip_ssl
        )
        end_time = time.time()

        if api is None:
            login_errors = [DeployError(context="Credentaisl", msg="failed")]
            print_errors(
                prefix=["login"],
                errors=login_errors,
                console=cli_context.console,
                elapsed_time=end_time - start_time,
            )
            return login_errors

        # Deploy challenges
        challenge_args = ChallengesArgs(
            api_key=api.session.access_token.value or "",
            url=ctfd_url,
            port=args.base_port,
            challenge=args.challenge,
            skip_ssl=skip_ssl,
        )

        challenge_status = challenges_cli(
            cli_context=cli_context,
            args=challenge_args,
        )
        if not challenge_status:
            return [DeployError(context="challenges", msg="failed to deploy")]

        if cli_context.console:
            cli_context.console.print("\nRunning at", ctfd_url)

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
        "-n", "--hostname", type=str, help="Hostname of CTFd", default=CHALLENGE_HOST
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
