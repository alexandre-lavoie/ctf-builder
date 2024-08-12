import typing

from .docker import DeployDocker


Deploy: typing.TypeAlias = typing.Union[DeployDocker]
