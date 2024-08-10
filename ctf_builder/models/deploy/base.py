import abc
import dataclasses
import typing

import docker
import pydantic

from ...error import LibError
from ..port import Port


def default_port_generator() -> typing.Generator[typing.Optional[int], None, None]:
    while True:
        yield None


@dataclasses.dataclass
class DeployContext:
    name: str
    root: str
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )
    network: typing.Optional[str] = dataclasses.field(default=None)
    host: typing.Optional[str] = dataclasses.field(default=None)
    port_generator: typing.Generator[typing.Optional[int], None, None] = (
        dataclasses.field(default_factory=lambda: default_port_generator())
    )


class BaseDeploy(abc.ABC, pydantic.BaseModel):
    """
    Automation to deploy challenges.
    """

    @abc.abstractmethod
    def get_ports(self) -> typing.Sequence[Port]:
        pass

    @abc.abstractmethod
    def has_healthcheck(cls, context: DeployContext) -> bool:
        pass

    @abc.abstractmethod
    def is_healthy(cls, context: DeployContext) -> bool:
        pass

    @abc.abstractmethod
    def start(
        self, context: DeployContext, skip_reuse: bool = True
    ) -> typing.Sequence[LibError]:
        pass

    @abc.abstractmethod
    def stop(
        self, context: DeployContext, skip_not_found: bool = True
    ) -> typing.Sequence[LibError]:
        pass
