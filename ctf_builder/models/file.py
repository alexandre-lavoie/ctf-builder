import dataclasses

import pydantic

from .path import FilePath


@dataclasses.dataclass(frozen=True)
class FileMapHandle:
    source: str
    destination: str


class FileMap(pydantic.BaseModel):
    """
    Mapping to move a source file to a destination.
    """

    source: FilePath = pydantic.Field(description="Path from source system")
    destination: FilePath = pydantic.Field(description="Path to target system")

    def build(self) -> FileMapHandle:
        return FileMapHandle(source=self.source.root, destination=self.destination.root)
