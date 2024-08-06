import os.path
import re
import socket
import sys
import typing


def solve() -> typing.Optional[str]:
    host = os.environ["CHALLENGE_HOST"]
    port = int(os.environ["CHALLENGE_PORT"])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        out = sock.recv(1024)

    return out.decode().strip()


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
