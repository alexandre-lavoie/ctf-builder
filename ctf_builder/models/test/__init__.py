import typing

from .docker import TestDocker


Test: typing.TypeAlias = typing.Union[TestDocker]
