import typing

from .docker import BuildDocker

Build: typing.TypeAlias = typing.Union[BuildDocker]
