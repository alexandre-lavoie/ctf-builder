import abc
import dataclasses
import typing

import pydantic

from .path import FilePath, PathContext


@dataclasses.dataclass(frozen=True)
class ArgumentContext:
    root: str


class BaseArguments(abc.ABC, pydantic.BaseModel):
    @abc.abstractmethod
    def build(self, context: ArgumentContext) -> typing.Optional[typing.Dict[str, str]]:
        pass


class EnvFileArguments(BaseArguments):
    """
    Arguments defined in a key/value part (env) file.
    """

    type: typing.Literal["env"]
    path: FilePath = pydantic.Field(description="Path to key/value pairs file")
    keys: typing.List[str] = pydantic.Field(
        default_factory=list,
        description="Keys to use in key/value pair file, empty selects all keys",
    )

    def build(self, context: ArgumentContext) -> typing.Optional[typing.Dict[str, str]]:
        if (path := self.path.resolve(PathContext(root=context.root))) is None:
            return None

        with open(path) as h:
            data = h.read()

        key_set = set(self.keys) if self.keys else None
        out = {}
        for line in data.split("\n"):
            if (offset := line.find("=")) == -1:
                continue

            key, value = line[:offset], line[offset + 1 :]
            if key_set and key not in key_set:
                continue

            out[key] = value

        return out


class ListArguments(BaseArguments):
    """
    Arguments defined as a list.
    """

    type: typing.Literal["list"]
    list: typing.List[str] = pydantic.Field(description="List of values")

    def build(self, context: ArgumentContext) -> typing.Optional[typing.Dict[str, str]]:
        return {str(i): v for i, v in enumerate(self.list)}


class MapArguments(BaseArguments):
    """
    Arguments defined as a map.
    """

    type: typing.Literal["map"]
    map: typing.Dict[str, str] = pydantic.Field(
        description="Dictionary of key/value pairs"
    )

    def build(self, context: ArgumentContext) -> typing.Optional[typing.Dict[str, str]]:
        return self.map


Arguments = typing.Union[EnvFileArguments, ListArguments, MapArguments]
