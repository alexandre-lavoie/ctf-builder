import abc
import dataclasses
import json
import os.path
import typing

import docker
import docker.errors

from ..schema import Builder, BuilderDocker
from ..error import BuildError

from .args import BuildArgs
from .file_map import BuildFileMap
from .utils import subclass_get 

@dataclasses.dataclass
class BuildContext:
    name: str
    path: str
    docker_client: typing.Optional[docker.APIClient] = dataclasses.field(default=None)

class BuildBuilder(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Builder]:
        return None

    @classmethod
    def get(cls, obj: Builder) -> typing.Optional[typing.Type["BuildBuilder"]]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(cls, context: BuildContext, builder: Builder) -> typing.Sequence[BuildError]:
        return []

class BuildBuilderDocker(BuildBuilder):
    @classmethod
    def __type__(cls) -> typing.Type[Builder]:
        return BuilderDocker

    @classmethod
    def to_docker_tag(cls, text: str) -> str:
        return text.replace(" ", "_").lower()

    @classmethod
    def build(cls, context: BuildContext, builder: BuilderDocker) -> typing.Sequence[BuildError]:
        if context.docker_client is None:
            return [BuildError("No docker client")]

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
        for res in context.docker_client.build(
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

        container = context.docker_client.create_container(image=tag)
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
                res, _ = context.docker_client.get_archive(container_id, source)
            except docker.errors.NotFound:
                errors.append(BuildError(f"file {source} not found in container"))
                continue

            with open(destination, "wb") as h:
                for chunk in res:
                    h.write(chunk)

        context.docker_client.remove_container(container_id, force=True)

        return errors

