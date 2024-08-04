import argparse
import dataclasses
import glob
import json
import os.path
import typing

import docker
import docker.errors
import docker.models.networks
import docker.types

from ..build import DeployContext, BuildDeployer
from ..error import DeployError, LibError, print_errors, get_exit_status
from ..parse import parse_track

@dataclasses.dataclass
class CliContext:
    network: docker.models.networks.Network
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(default=None)

def stop_challenge(json_path: str, cli_context: CliContext) -> typing.Sequence[typing.Union[LibError]]:
    if not os.path.exists(json_path):
        return [DeployError("file not found")]

    if not os.path.isfile(json_path):
        return [DeployError("not a file")]

    try:
        with open(json_path) as h:
            data = json.load(h)
    except:
        return [DeployError("invalid JSON")]

    track, errors = parse_track(data)
    if errors:
        return errors

    errors = []
    for i, deployer in enumerate(track.deploy):
        deploy_context = DeployContext(
            name=f"{cli_context.network.name}_{track.name}_{i}",
            path=os.path.dirname(json_path),
            docker_client=cli_context.docker_client,
            network=cli_context.network.name
        )

        db = BuildDeployer.get(deployer)
        if db is None:
            errors.append(DeployError(f"unhandled {type(deployer)}"))
            continue

        errors += db.stop(deploy_context, deployer)

    return errors

def stop_challenges(root: str, cli_context: CliContext) -> typing.Mapping[str, typing.Sequence[LibError]]:
    if not os.path.isdir(root):
        return {
            "": [DeployError("challenges directory not found")]
        }

    out = {}
    for file in glob.glob("**/challenge.json", root_dir=root, recursive=True):
        path = os.path.join(root, file)

        out[path] = stop_challenge(path, cli_context=cli_context)

    return out

def get_network(client: docker.DockerClient, name: typing.Optional[str] = None) -> docker.models.networks.Network:
    try:
        return client.networks.get(name)
    except docker.errors.NotFound:
        return None
    except docker.errors.APIError:
        return None

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-c", "--challenge", choices=challenges, help="Name of challenge to stop", default=None)
    parser.add_argument("-n", "--network", action="append", help="Names of network to stop", default=[])

def cli(args, root_directory: str) -> bool:
    challenge_directory = os.path.join(root_directory, "challenges")

    docker_client = docker.from_env()

    args_networks = args.network
    if not args_networks:
        args_networks.append("ctf-builder_deploy")

    all_errors = []
    for arg_network in args_networks:
        network = get_network(docker_client, arg_network)
        if network is None:
            errors = [DeployError(f"network not found")]
            all_errors += errors
            print_errors(arg_network, errors)
            continue

        cli_context = CliContext(
            network=network,
            docker_client=docker_client
        )

        if args.challenge:
            path = os.path.join(challenge_directory, args.challenge, "challenge.json")
            errors = stop_challenge(
                path,
                cli_context=cli_context
            )

            all_errors += errors

            if len(args_networks) > 1:
                prefix = network.name
            else:
                prefix = None

            print_errors(prefix, errors)
        else:
            for path, errors in stop_challenges(
                challenge_directory,
                cli_context=cli_context
            ).items():
                all_errors += errors

                if len(args_networks) > 1:
                    prefix = f"{network.name} > {os.path.basename(os.path.dirname(path))}"
                else:
                    prefix = os.path.basename(os.path.dirname(path))

                print_errors(prefix, errors)

    return get_exit_status(all_errors)

