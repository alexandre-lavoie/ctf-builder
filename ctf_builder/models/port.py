import abc
import dataclasses
import typing

import pydantic

from ..k8s.models import K8sPortProtocol


@dataclasses.dataclass(frozen=True)
class ConnectionContext:
    host: str
    port: int
    path: typing.Optional[str] = dataclasses.field(default=None)


def uri_connection_string(protocol: str, context: ConnectionContext) -> str:
    return f"{protocol}://{context.host}:{context.port}{context.path or ''}"


class BasePort(abc.ABC, pydantic.BaseModel):
    value: int = pydantic.Field(description="Port value")
    public: bool = pydantic.Field(
        default=False, description="Is this port exposed to the internet?"
    )

    @abc.abstractmethod
    def connection_string(self, context: ConnectionContext) -> str:
        pass

    @abc.abstractmethod
    def k8s_port_protocol(self) -> K8sPortProtocol:
        pass


class HTTPPort(BasePort):
    type: typing.Literal["http"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("http", context)

    def k8s_port_protocol(self) -> K8sPortProtocol:
        return K8sPortProtocol.TCP


class HTTPSPort(BasePort):
    type: typing.Literal["https"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("https", context)

    def k8s_port_protocol(self) -> K8sPortProtocol:
        return K8sPortProtocol.TCP


class TCPPort(BasePort):
    type: typing.Literal["tcp"]

    def connection_string(self, context: ConnectionContext) -> str:
        return f"nc {context.host} {context.port}"

    def k8s_port_protocol(self) -> K8sPortProtocol:
        return K8sPortProtocol.TCP


class UDPPort(BasePort):
    type: typing.Literal["udp"]

    def connection_string(self, context: ConnectionContext) -> str:
        return f"nc -u {context.host} {context.port}"

    def k8s_port_protocol(self) -> K8sPortProtocol:
        return K8sPortProtocol.UDP


class WSPort(BasePort):
    type: typing.Literal["ws"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("ws", context)

    def k8s_port_protocol(self) -> K8sPortProtocol:
        return K8sPortProtocol.TCP


class WSSPort(BasePort):
    type: typing.Literal["wss"]

    def connection_string(self, context: ConnectionContext) -> str:
        return uri_connection_string("wss", context)

    def k8s_port_protocol(self) -> K8sPortProtocol:
        return K8sPortProtocol.TCP


Port = typing.Union[HTTPPort, HTTPSPort, TCPPort, UDPPort, WSPort, WSSPort]
