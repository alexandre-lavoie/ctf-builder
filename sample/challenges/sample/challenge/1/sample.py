import os
import socket

def main(flag: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("0.0.0.0", 9001))
        sock.listen()

        print("Listening on 0.0.0.0:9001")

        while True:
            connection, address = sock.accept()
            connection.send(flag.encode())
            connection.close()

def cli() -> int:
    flag = os.environ.get("FLAG2")
    if flag is None:
        print("FLAG2 not defined")
        return 1

    main(flag)

    return 0

if __name__ == "__main__":
    exit(cli())
