import dataclasses
import datetime
import re
import time
import typing

import docker
import docker.errors
import docker.models.containers
import requests

from .error import DeployError, LibError


VERSION = "/api/v1"
NONCE_RE = re.compile(r"<input id=\"nonce\".+?value=\"(.+?)\">")
CSRF_RE = re.compile(r"'csrfNonce': \"(.*?)\"")


@dataclasses.dataclass(frozen=True)
class CTFdAPI:
    url: str
    api_key: str

    def __headers(self) -> typing.Dict[str, str]:
        return {"Authorization": f"Token {self.api_key}"}

    def __url(self, path: str) -> str:
        return f"{self.url}{VERSION}{path}"

    def get(
        self, path: str, data: typing.Optional[typing.Dict[str, typing.Any]] = None
    ) -> requests.Response:
        return requests.get(
            url=self.__url(path),
            headers={**self.__headers(), "Content-Type": "application/json"},
            params=data,
        )

    def post(self, path: str, data: typing.Dict[str, typing.Any]) -> requests.Response:
        return requests.post(url=self.__url(path), headers=self.__headers(), json=data)

    def post_data(
        self, path: str, data: typing.Dict[str, typing.Any], files: typing.Any
    ) -> requests.Response:
        return requests.post(
            url=self.__url(path),
            headers=self.__headers(),
            data=data,
            files=files,
        )

    def patch(self, path: str, data: typing.Dict[str, typing.Any]) -> requests.Response:
        return requests.patch(url=self.__url(path), headers=self.__headers(), json=data)

    def delete(self, path: str) -> requests.Response:
        return requests.delete(
            url=self.__url(path),
            headers={**self.__headers(), "Content-Type": "application/json"},
        )


def read_nonce(sess: requests.Session, url: str) -> typing.Optional[str]:
    res = sess.get(url)

    match = NONCE_RE.findall(res.text)

    return match[0] if match else None


def read_csrf(sess: requests.Session, url: str) -> typing.Optional[str]:
    res = sess.get(url)

    match = CSRF_RE.findall(res.text)

    return match[0] if match else None


def generate_key(
    url: str, name: str, password: str
) -> typing.Optional[typing.Tuple[int, str]]:
    sess = requests.Session()

    nonce = read_nonce(sess, f"{url}/login")

    res = sess.post(
        f"{url}/login", data={"name": name, "password": password, "nonce": nonce}
    )
    if res.status_code != 200:
        return None

    csrf = read_csrf(sess, f"{url}/settings")

    expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        days=1
    )

    res = sess.post(
        f"{url}/api/v1/tokens",
        headers={"CSRF-Token": csrf},
        json={
            "description": "Created via ctf-builder",
            "expiration": expiration.date().isoformat(),
        },
    )
    if res.status_code != 200:
        return None

    data = res.json()["data"]

    return data["id"], data["value"]


def ctfd_errors(res: requests.Response, context: str) -> typing.Sequence[LibError]:
    if res.status_code == 200:
        return []

    data: typing.Dict[str, typing.Any] = res.json()

    return [
        DeployError(
            context=context,
            msg="failed to deploy",
            error=ValueError(data.get("message") or data.get("errors")),
        )
    ]


def ctfd_container(
    docker_client: docker.DockerClient, port: int, name: typing.Optional[str] = None
) -> typing.Tuple[
    typing.Optional[docker.models.containers.Container], typing.Sequence[LibError]
]:
    try:
        container: docker.models.containers.Container = docker_client.containers.run(
            name=name,
            image="ctfd/ctfd",
            ports={"8000": port},
            detach=True,
            remove=True,
            healthcheck={
                "test": "python -c \"import requests; requests.get('http://localhost:8000/')\" || exit 1",
                "interval": 1_000_000_000,
                "timeout": 1_000_000_000,
                "retries": 10,
                "start_period": 1_000_000_000,
            },
        )
    except Exception as e:
        return None, [DeployError(context="Container", msg="failed to deploy", error=e)]

    try:
        # Wait for container to be healthy
        for _ in range(40):
            container.reload()

            if container.health == "healthy":
                break

            time.sleep(0.5)
        else:
            raise Exception("Not healthy")
    except Exception as e:
        try:
            container.remove(force=True)
        except:
            pass

        return None, [
            DeployError(context="Container", msg="failed to become healthy", error=e)
        ]

    return container, []
