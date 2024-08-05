import os.path
import re
import subprocess
import socket
import typing


def solve_0() -> typing.Optional[str]:
    exe_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "build", "0", "sample"
    )

    proc = subprocess.run([exe_path], capture_output=True)

    return proc.stdout.decode().strip()[6:]


def solve_1() -> typing.Optional[str]:
    host = os.environ["CHALLENGE_HOST"]
    port = int(os.environ["CHALLENGE_PORT"])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        out = sock.recv(1024)

    return out.decode().strip()


def cli() -> int:
    if (solve := globals()[f"solve_{os.environ['CHALLENGE_ID']}"]()) is None:
        return 1

    if not (flag := os.environ.get("FLAG")):
        return 0

    if os.environ.get("FLAG_TYPE") == "regex":
        return 0 if re.match(flag, solve) else 1

    return 0 if solve == flag else 1


if __name__ == "__main__":
    exit(cli())
