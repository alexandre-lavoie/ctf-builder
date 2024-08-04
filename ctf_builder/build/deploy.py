import abc
import dataclasses
import typing

import docker

from ..schema import Deployer, DeployerDocker
from ..error import DeployError

from .utils import subclass_get

@dataclasses.dataclass
class DeployContext:
    docker_client: typing.Optional[docker.APIClient] = dataclasses.field(default=None)

class BuildDeployer(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Deployer]:
        return None
    
    @classmethod
    def get(cls, obj: Deployer) -> typing.Optional[typing.Type["BuildDeployer"]]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(cls, context: DeployContext, builder: Deployer) -> typing.Sequence[DeployError]:
        return []

class BuildDeployerDocker(abc.ABC):
    @classmethod
    def __type__(cls) -> typing.Type[Deployer]:
        return DeployerDocker

    @classmethod
    def build(cls, context: DeployContext, builder: Deployer) -> typing.Sequence[DeployError]:
        return []
