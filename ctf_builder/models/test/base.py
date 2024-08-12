import abc
import dataclasses
import typing

import docker
import pydantic

from ...error import LibError
from ..deploy import Deploy


if typing.TYPE_CHECKING:
    from ..challenge import Challenge


@dataclasses.dataclass(frozen=True)
class TestContext:
    root: str
    name: str
    challenges: typing.Sequence["Challenge"]
    deployers: typing.Sequence[Deploy]
    network: typing.Optional[str]
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


class BaseTest(abc.ABC, pydantic.BaseModel):
    """
    Automation to test challenges
    """

    @abc.abstractmethod
    def build(self, context: TestContext) -> typing.Sequence[LibError]:
        pass
