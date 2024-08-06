import dataclasses
import requests
import typing

VERSION = "/api/v1"


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
