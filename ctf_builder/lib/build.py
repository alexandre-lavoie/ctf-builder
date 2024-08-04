import abc
import dataclasses
import glob
import io
import json
import os.path
import typing
import zipfile

import docker
import docker.errors

from .error import BuildError
from .schema import *

T = typing.TypeVar("T")
U = typing.TypeVar("U")
def subclass_get(cls: typing.Type[T], obj: U) -> typing.Type[T]:
    for subclass in cls.__subclasses__():
        if subclass.__type__() == type(obj):
            return subclass
    else:
        return None

@dataclasses.dataclass
class BuildContext:
    name: str
    path: str

class BuildArgs(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Args]:
        return None

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, args: Args) -> typing.Optional[typing.Dict[str, str]]:
        return {}

    @classmethod
    def get(cls, obj: Builder) -> typing.Optional[typing.Type["BuildArgs"]]:
        return subclass_get(cls, obj)

class BuildArgsList(BuildArgs):
    @classmethod
    def __type__(cls) -> typing.Type[Args]:
        return ArgsList
    
    @classmethod
    def build(cls, root: str, args: ArgsList) -> typing.Optional[typing.Dict[str, str]]:
        return {str(i):v for i, v in enumerate(args.list)}

class BuildArgsMap(BuildArgs):
    @classmethod
    def __type__(cls) -> typing.Type[Args]:
        return ArgsMap
    
    @classmethod
    def build(cls, root: str, args: ArgsMap) -> typing.Optional[typing.Dict[str, str]]:
        return args.map

class BuildArgsEnv(BuildArgs):
    @classmethod
    def __type__(cls) -> typing.Type[Args]:
        return ArgsEnv

    @classmethod
    def build(cls, root: str, args: ArgsEnv) -> typing.Optional[typing.Dict[str, str]]:
        path = args.path.resolve(root)
        if path is None:
            return None
        
        with open(path) as h:
            data = h.read()

        key_set = set(args.keys) if args.keys else None
        out = {}
        for line in data.split("\n"):
            try:
                offset = line.index("=")
            except ValueError:
                continue

            key, value = line[:offset], line[offset + 1:]
            if key_set and key not in key_set:
                continue

            out[key] = value

        return out

class BuildFileMap:
    @classmethod
    def build(cls, file_map: FileMap) -> typing.Optional[typing.Tuple[str, str]]:
        return (file_map.source.value, file_map.destination.value)

class BuildBuilder(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Builder]:
        return None

    @classmethod
    @abc.abstractmethod
    def build(cls, context: BuildContext, builder: Builder) -> typing.Sequence[BuildError]:
        return []

    @classmethod
    def get(cls, obj: Builder) -> typing.Optional[typing.Type["BuildBuilder"]]:
        return subclass_get(cls, obj)

class BuildBuilderDocker(BuildBuilder):
    @classmethod
    def __type__(cls) -> typing.Type[Builder]:
        return BuilderDocker

    @classmethod
    def to_docker_tag(cls, text: str) -> str:
        return text.replace(" ", "_").lower()

    @classmethod
    def build(cls, context: BuildContext, builder: BuilderDocker) -> typing.Sequence[BuildError]:
        client = docker.APIClient()

        if builder.path is None:
            dockerfile = os.path.join(context.path, "Dockerfile")
        else:
            dockerfile = builder.path.resolve(context.path)

        if dockerfile is None or not os.path.exists(dockerfile):
            return [BuildError("Dockerfile is invalid")]

        tag = cls.to_docker_tag(context.name)

        errors = []
        build_args = {}
        for args in builder.args:
            ba = BuildArgs.get(args)
            if ba is None:
                errors.append(BuildError(f"unhandled {type(args)}"))
                continue

            arg_map = ba.build(context.path, args)
            if arg_map is None:
                errors.append(f"invalid {type(args)}")
                break 

            for key, value in arg_map.items():
                build_args[key] = value

        cwd = os.path.abspath(context.path)

        is_ok = False
        for res in client.build(
            path=cwd,
            dockerfile=os.path.abspath(dockerfile),
            tag=tag,
            buildargs=build_args
        ):
            data = json.loads(res.decode())

            if "aux" in data:
                is_ok = True

        if not is_ok:
            return errors + [BuildError("Dockerfile not built")]

        container = client.create_container(image=tag)
        if container is None or "Id" not in container:
            return False
        container_id: str = container["Id"] 

        for i, file_map in enumerate(builder.files):
            source, destination = BuildFileMap.build(file_map)
            destination = os.path.join(cwd, destination)

            if os.path.isdir(destination):
                errors.append(BuildError(f"{i}.destination is a directory"))
                continue

            os.makedirs(os.path.dirname(destination), exist_ok=True)

            try:
                res, _ = client.get_archive(container_id, source)
            except docker.errors.NotFound:
                errors.append(BuildError(f"file {source} not found in container"))
                continue

            with open(destination, "wb") as h:
                for chunk in res:
                    h.write(chunk)

        client.remove_container(container_id)

        return errors

class BuildFlag:
    @classmethod
    def build(cls, root: str, flag: ChallengeFlag) -> typing.List[str]:
        ba = BuildArgs.get(flag.values)
        if ba is None:
            return []

        m = ba.build(root, flag.values)
        if m is None:
            return []

        return list(m.values())

class BuildTranslation(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Translation]:
        return None
    
    @classmethod
    @abc.abstractmethod
    def priority(cls) -> int:
        return 0

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, translation: Translation) -> typing.Optional[str]:
        return []
    
    @classmethod
    def build_common(cls, root: str, translation: Translation) -> typing.Optional[str]:
        path = translation.path.resolve(root)
        if path is None:
            return False
        
        with open(path) as h:
            return h.read().strip()

    @classmethod
    def get(cls, obj: Translation) -> typing.Optional[typing.Type["BuildTranslation"]]:
        return subclass_get(cls, obj)

class BuildTranslationFrench(BuildTranslation):
    @classmethod
    def __type__(cls) -> typing.Type[Translation]:
        return TranslationFrench

    @classmethod
    def priority(cls) -> int:
        return 1

    @classmethod
    def build(cls, root: str, description: TranslationFrench) -> typing.Optional[str]:
        return cls.build_common(root, description)

class BuildTranslationEnglish(BuildTranslation):
    @classmethod
    def __type__(cls) -> typing.Type[Translation]:
        return TranslationEnglish

    @classmethod
    def priority(cls) -> int:
        return 2

    @classmethod
    def build(cls, root: str, description: TranslationEnglish) -> typing.Optional[str]:
        return cls.build_common(root, description)

class BuildAttachment(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Attachment]:
        return None

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, attachment: Attachment) -> typing.Optional[typing.Tuple[str, io.BytesIO]]:
        return []

    @classmethod
    def get(cls, obj: Attachment) -> typing.Optional[typing.Type["BuildAttachment"]]:
        return subclass_get(cls, obj)

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
