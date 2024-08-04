import argparse
import glob
import json
import os
import os.path
import typing

import docker

from ..build import BuildBuilder, BuildContext
from ..error import BuildError, SkipError, LibError, print_errors, get_exit_status
from ..parse import parse_track

def build_challenge(json_path: str, skip_active: bool, docker_client: typing.Optional[docker.DockerClient] = None) -> typing.Sequence[typing.Union[LibError]]:
    if not os.path.exists(json_path):
        return [BuildError("file not found")]

    if not os.path.isfile(json_path):
        return [BuildError("not a file")]

    try:
        with open(json_path) as h:
            data = json.load(h)
    except:
        return [BuildError("invalid JSON")]

    track, errors = parse_track(data)
    if errors:
        return errors

    if not skip_active and not track.active:
        return [SkipError()]

    context = BuildContext(
        path=os.path.dirname(json_path),
        docker_client=docker_client
    )

    errors = []
    for builder in track.build:
        bb = BuildBuilder.get(builder)
        if bb is None:
            errors.append(BuildError(f"unhandled {type(builder)}"))
            continue

        errors += bb.build(context, builder)

    return errors

def build_challenges(root: str, docker_client: typing.Optional[docker.DockerClient] = None) -> typing.Mapping[str, typing.Sequence[LibError]]:
    if not os.path.isdir(root):
        return {
            "": [BuildError("challenges directory not found")]
        }

    out = {}
    for file in glob.glob("**/challenge.json", root_dir=root, recursive=True):
        path = os.path.join(root, file)

        out[path] = build_challenge(path, skip_active=False, docker_client=docker_client)

    return out

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-c", "--challenge", choices=challenges, help="Name of challenge to build", default=None)

def cli(args, root_directory: str) -> bool:
    challenge_directory = os.path.join(root_directory, "challenges")

    docker_client = docker.from_env()

    all_errors = []
    if args.challenge:
        path = os.path.join(challenge_directory, args.challenge, "challenge.json")
        all_errors = build_challenge(path, skip_active=True, docker_client=docker_client)

        print_errors(None, all_errors)
    else:
        for path, errors in build_challenges(challenge_directory, docker_client=docker_client).items():
            all_errors += errors
            print_errors(os.path.basename(os.path.dirname(path)), errors)

    return get_exit_status(all_errors)
