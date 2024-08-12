import abc
import dataclasses
import glob
import io
import os.path
import typing
import zipfile

import pydantic

from .path import DirectoryPath, FilePath, PathContext


@dataclasses.dataclass(frozen=True)
class AttachmentContext:
    root: str


@dataclasses.dataclass(frozen=True)
class AttachmentHandle:
    name: str
    data: typing.BinaryIO


class BaseAttachment(abc.ABC, pydantic.BaseModel):
    """
    Resource that can be uploaded.
    """

    @abc.abstractmethod
    def build(self, context: AttachmentContext) -> typing.Optional[AttachmentHandle]:
        pass


class DirectoryAttachment(BaseAttachment):
    """
    Directory resource. Intended to be used to select files recursively.
    """

    type: typing.Literal["directory"]
    path: DirectoryPath = pydantic.Field(
        description="Path to attachment directory that will be converted to zip"
    )
    name: typing.Optional[str] = pydantic.Field(
        default=None, description="Name of the attachment, if not directory.zip"
    )

    def build(self, context: AttachmentContext) -> typing.Optional[AttachmentHandle]:
        if (path := self.path.resolve(PathContext(root=context.root))) is None:
            return None

        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as zh:
            for rel_path in glob.glob("**/*", root_dir=path, recursive=True):
                abs_path = os.path.join(path, rel_path)
                if not os.path.isfile(abs_path):
                    continue

                with open(abs_path, "rb") as rh, zh.open(rel_path, "w") as wh:
                    wh.write(rh.read())
        data.seek(0)

        if self.name is not None:
            name = self.name
        else:
            name = os.path.basename(path) + ".zip"

        return AttachmentHandle(name=name, data=data)


class FileAttachment(BaseAttachment):
    """
    File resource.
    """

    type: typing.Literal["file"]
    path: FilePath = pydantic.Field(description="Path to attachment file")
    name: typing.Optional[str] = pydantic.Field(
        default=None, description="Name of the attachment, if not file.ext"
    )

    def build(self, context: AttachmentContext) -> typing.Optional[AttachmentHandle]:
        if (path := self.path.resolve(PathContext(root=context.root))) is None:
            return None

        with open(path, "rb") as h:
            data = h.read()

        if self.name is not None:
            name = self.name
        else:
            name = os.path.basename(path)

        return AttachmentHandle(name=name, data=io.BytesIO(data))


Attachment: typing.TypeAlias = typing.Union[DirectoryAttachment, FileAttachment]
