import abc
import dataclasses
import typing

import docker
import pydantic

from ...error import LibError


@dataclasses.dataclass(frozen=True)
class BuildContext:
    root: str
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


class BaseBuild(abc.ABC, pydantic.BaseModel):
    """
    Automation to build challenges.
    """

    @abc.abstractmethod
    def build(self, context: BuildContext) -> typing.Sequence[LibError]:
        pass
