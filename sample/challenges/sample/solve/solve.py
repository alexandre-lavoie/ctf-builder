import argparse
import dataclasses
import os.path
import subprocess
import typing

#
# Solve
#

def solve_0(context: "Context") -> str:
    exe_path = os.path.join(context.path, "sample1")

    proc = subprocess.run([exe_path], capture_output=True)

    print(proc.stdout)

def solve_1(context: "Context") -> str:
    pass

#
# CLI
#

@dataclasses.dataclass
class Context:
    path: str

def solvers() -> typing.Dict[int, typing.Callable[[Context], str]]:
    out = {}
    for k, v in globals().items():
        if k.startswith("solve_"):
            out[k[6:]] = v

    return out

def solve(challenge: int, context: Context) -> typing.Optional[str]:
    solver = solvers().get(challenge)
    if not solver:
        return None

    return solver(context)

def cli() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("-c", "--challenge", choices=solvers().keys(), help="Challenge to solve", required=True)
    parser.add_argument("-p", "--path", help="Path to handout", default=os.path.join("", "..", "handout"))
    parser.add_argument("-f", "--flag", help="Flag to check against", default=None)

    args = parser.parse_args()

    context = Context(
        path=args.path
    )

    flag = solve(args.challenge, context)
    if flag is None:
        return 1

    if not args.flag:
        return 0

    return 0 if flag == args.flag else 1

if __name__ == "__main__":
    exit(cli())
