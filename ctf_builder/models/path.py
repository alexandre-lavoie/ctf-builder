import abc
import dataclasses
import os.path
import typing

import pydantic


@dataclasses.dataclass(frozen=True)
class PathContext:
    root: str


class BasePath(abc.ABC, pydantic.BaseModel):
    @abc.abstractmethod
    def resolve(self, context: PathContext) -> typing.Optional[str]:
        pass


class DirectoryPath(pydantic.RootModel[str]):
    root: str = pydantic.Field(description="Path to directory")

    def resolve(self, context: PathContext) -> typing.Optional[str]:
        path = os.path.join(context.root, self.root)

        if not os.path.isdir(path):
            return None

        return path


class FilePath(pydantic.RootModel[str]):
    root: str = pydantic.Field(description="Path to file")

    def resolve(self, context: PathContext) -> typing.Optional[str]:
        path = os.path.join(context.root, self.root)

        if not os.path.isfile(path):
            return None

        return path


Path = typing.Union[DirectoryPath, FilePath]
