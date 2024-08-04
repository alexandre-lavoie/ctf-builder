import abc
import glob
import io
import os.path
import typing
import zipfile

from ..schema import Attachment, AttachmentFile, AttachmentDirectory

from .utils import subclass_get

class BuildAttachment(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Attachment]:
        return None

    @classmethod
    def get(cls, obj: Attachment) -> typing.Optional[typing.Type["BuildAttachment"]]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, attachment: Attachment) -> typing.Optional[typing.Tuple[str, io.BytesIO]]:
        return []

class BuildAttachmentFile(BuildAttachment):
    @classmethod
    def __type__(cls) -> typing.Type[Attachment]:
        return AttachmentFile

    @classmethod
    def build(cls, root: str, file: AttachmentFile) -> typing.Optional[typing.Tuple[str, io.BytesIO]]:
        path = file.path.resolve(root)
        if path is None:
            return None
        
        with open(path, "rb") as h:
            data = h.read()

        if file.name is not None:
            name = file.name
        else:
            name = os.path.basename(path)

        return name, io.BytesIO(data)

class BuildAttachmentDirectory(BuildAttachment):
    @classmethod
    def __type__(cls) -> typing.Type[Attachment]:
        return AttachmentDirectory

    @classmethod
    def build(cls, root: str, directory: AttachmentDirectory) -> typing.Optional[typing.Tuple[str, io.BytesIO]]:
        path = directory.path.resolve(root)
        if path is None:
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

        if directory.name is not None:
            name = directory.name
        else:
            name = os.path.basename(path) + ".zip"

        return name, data
