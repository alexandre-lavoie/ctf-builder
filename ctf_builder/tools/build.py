import argparse
import glob
import json
import os
import os.path
import typing

from ..lib import *

def build_challenge(json_path: str, skip_active: bool) -> typing.Sequence[typing.Union[LibError]]:
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

    errors = []
    for i, builder in enumerate(track.build):
        context = BuildContext(
            name=f"{track.name}-{i}",
            path=os.path.dirname(json_path)
        )

        bb = BuildBuilder.get(builder)
        if bb is None:
            errors.append(BuildError(f"unhandled {type(builder)}"))
            continue

        errors += bb.build(context, builder)

    return errors

def build_challenges(root: str) -> typing.Mapping[str, typing.Sequence[LibError]]:
    if not os.path.isdir(root):
        return {
            "": [BuildError("challenges directory not found")]
        }

    out = {}
    for file in glob.glob("**/challenge.json", root_dir=root, recursive=True):
        path = os.path.join(root, file)

        out[path] = build_challenge(path, skip_active=False)

    return out

def cli_args(parser: argparse.ArgumentParser, root_directory: str):
    challenge_directory = os.path.join(root_directory, "challenges")

    challenges = [file for file in glob.glob("*", root_dir=challenge_directory)]

    parser.add_argument("-c", "--challenge", choices=challenges, help="Name of challenge to build", default=None)

def cli(args, root_directory: str) -> bool:
    challenge_directory = os.path.join(root_directory, "challenges")

    if args.challenge:
        path = os.path.join(challenge_directory, args.challenge, "challenge.json")
        errors = build_challenge(path, skip_active=True)

        is_ok = False if errors else True
        print_errors(None, errors)
    else:
        is_ok = True
        for path, errors in build_challenges(challenge_directory).items():
            if errors:
                is_ok = False

            print_errors(path, errors)

    return is_ok
