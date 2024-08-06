import os.path
import re
import subprocess
import sys
import typing


def solve() -> typing.Optional[str]:
    exe_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "build", "challenge"
    )

    proc = subprocess.run([exe_path], capture_output=True)

    return proc.stdout.decode().strip()[6:]


def cli() -> int:
    if (solution := solve()) is None:
        return 1

    if not (flag := os.environ.get("FLAG")):
        return 0

    if os.environ.get("FLAG_TYPE") == "regex":
        is_ok = re.match(flag, solution)
    else:
        is_ok = solution == flag

    if not is_ok:
        print(f"FAIL: {solution}", file=sys.stderr)

    return 0 if is_ok else 1


if __name__ == "__main__":
    exit(cli())
