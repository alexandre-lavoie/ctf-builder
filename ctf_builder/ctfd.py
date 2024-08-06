import dataclasses
import datetime
import re
import typing

import requests


VERSION = "/api/v1"
NONCE_RE = re.compile(r"<input id=\"nonce\".+?value=\"(.+?)\">")
CSRF_RE = re.compile(r"'csrfNonce': \"(.*?)\"")


@dataclasses.dataclass(frozen=True)
class CTFdAPI:
    url: str
    api_key: str

    def __headers(self) -> typing.Dict[str, str]:
        return {"Authorization": f"Token {self.api_key}"}

    def get(self, path: str) -> requests.Response:
        return requests.get(f"{self.url}{VERSION}{path}", headers=self.__headers())

    def post(self, path: str, data: typing.Dict[str, typing.Any]) -> requests.Response:
        return requests.post(
            f"{self.url}{VERSION}{path}", headers=self.__headers(), json=data
        )

    def post_data(
        self, path: str, data: typing.Dict[str, typing.Any], files: typing.Any
    ) -> requests.Response:
        return requests.post(
            f"{self.url}{VERSION}{path}",
            headers=self.__headers(),
            data=data,
            files=files,
        )

    def patch(self, path: str, data: typing.Dict[str, typing.Any]) -> requests.Response:
        return requests.patch(
            f"{self.url}{VERSION}{path}", headers=self.__headers(), json=data
        )

    def delete(
        self, path: str, data: typing.Dict[str, typing.Any]
    ) -> requests.Response:
        return requests.delete(
            f"{self.url}{VERSION}{path}", headers=self.__headers(), json=data
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
