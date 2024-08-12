import dataclasses
import typing

import requests

from .models import CTFdAccessToken


VERSION = "/api/v1"


@dataclasses.dataclass(frozen=True)
class CTFdSession:
    url: str
    access_token: CTFdAccessToken

    def __headers(self) -> typing.Dict[str, str]:
        return {"Authorization": f"Token {self.access_token.value}"}

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
