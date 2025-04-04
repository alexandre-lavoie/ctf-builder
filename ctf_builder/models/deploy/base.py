import abc
import dataclasses
import typing

import docker
import pydantic

from ...error import LibError
from ...k8s.models import K8sImagePullPolicy, K8sKind
from ..port import Port


def default_port_generator() -> typing.Generator[typing.Optional[int], None, None]:
    while True:
        yield None


@dataclasses.dataclass
class DockerDeployContext:
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
    repository: typing.Optional[str] = dataclasses.field(default=None)
    tag: bool = dataclasses.field(default=True)


@dataclasses.dataclass
class K8sDeployContext:
    name: str
    root: str
    track: str
    repository: typing.Optional[str] = dataclasses.field(default=None)
    port_generator: typing.Generator[typing.Optional[int], None, None] = (
        dataclasses.field(default_factory=lambda: default_port_generator())
    )
    image_pull_policy: K8sImagePullPolicy = K8sImagePullPolicy.Always


class BaseDeploy(abc.ABC, pydantic.BaseModel):
    """
    Automation to deploy challenges.
    """

    @abc.abstractmethod
    def get_ports(self) -> typing.Sequence[Port]:
        pass

    @abc.abstractmethod
    def has_healthcheck(cls) -> bool:
        pass

    @abc.abstractmethod
    def docker_healthcheck(cls, context: DockerDeployContext) -> bool:
        pass

    @abc.abstractmethod
    def docker_start(
        self, context: DockerDeployContext, skip_reuse: bool = True
    ) -> typing.Sequence[LibError]:
        pass

    @abc.abstractmethod
    def docker_stop(
        self, context: DockerDeployContext, skip_not_found: bool = True
    ) -> typing.Sequence[LibError]:
        pass

    @abc.abstractmethod
    def docker_deploy(self, context: DockerDeployContext) -> typing.Sequence[LibError]:
        pass

    @abc.abstractmethod
    def k8s_build(
        self, context: K8sDeployContext
    ) -> typing.Tuple[typing.Optional[K8sKind], typing.Sequence[LibError]]:
        pass
