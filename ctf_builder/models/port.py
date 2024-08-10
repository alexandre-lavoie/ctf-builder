import abc
import dataclasses
import typing

import pydantic


@dataclasses.dataclass(frozen=True)
class ConnectionContext:
    host: str
    port: int
    path: typing.Optional[str] = dataclasses.field(default=None)


def uri_connection_string(protocol: str, context: ConnectionContext) -> str:
    return f"{protocol}://{context.host}:{context.port}{context.path or ''}"


class BasePort(abc.ABC, pydantic.BaseModel):
    value: int

    @abc.abstractmethod
    def connection_string(self, context: ConnectionContext) -> str:
        pass


class HTTPPort(BasePort):
    type: typing.Literal["http"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("http", context)


class HTTPSPort(BasePort):
    type: typing.Literal["https"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("https", context)


class TCPPort(BasePort):
    type: typing.Literal["tcp"]

    def connection_string(self, context: ConnectionContext) -> str:
        return f"nc {context.host} {context.port}"


class UDPPort(BasePort):
    type: typing.Literal["udp"]

    def connection_string(self, context: ConnectionContext) -> str:
        return f"nc -u {context.host} {context.port}"


class WSPort(BasePort):
    type: typing.Literal["ws"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("ws", context)


class WSSPort(BasePort):
    type: typing.Literal["wss"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("wss", context)


Port: typing.TypeAlias = typing.Union[
    HTTPPort, HTTPSPort, TCPPort, UDPPort, WSPort, WSSPort
]
