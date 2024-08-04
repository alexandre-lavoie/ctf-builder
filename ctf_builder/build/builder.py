import abc
import dataclasses
import os.path
import typing

import docker
import docker.errors

from ..error import BuildError
from ..logging import LOG
from ..schema import Builder, BuilderDocker

from .args import BuildArgs
from .file_map import BuildFileMap
from .utils import subclass_get 

@dataclasses.dataclass
class BuildContext:
    path: str
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(default=None)

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
    def build(cls, context: BuildContext, builder: BuilderDocker) -> typing.Sequence[BuildError]:
        if context.docker_client is None:
            return [BuildError("No docker client")]

        if builder.path is None:
            dockerfile = os.path.join(context.path, "Dockerfile")
        else:
            dockerfile = builder.path.resolve(context.path)

        if dockerfile is None or not os.path.exists(dockerfile):
            return [BuildError("Dockerfile is invalid")]
        
        dockerfile = os.path.abspath(dockerfile)

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

        try:
            image, logs = context.docker_client.images.build(
                path=os.path.dirname(dockerfile),
                dockerfile=dockerfile,
                buildargs=build_args
            )

            for log in logs:
                if "stream" not in log:
                    continue

                LOG.info(log["stream"].strip())
        except docker.errors.BuildError as e:
            return errors + [BuildError(f"Dockerfile build failed > {e}")]

        try:
            container = context.docker_client.containers.create(image=image)
        except docker.errors.APIError as e:
            return errors + [BuildError(f"Dockerfile create failed > {e}")]

        for i, file_map in enumerate(builder.files):
            source, destination = BuildFileMap.build(file_map)
            destination = os.path.join(os.path.abspath(context.path), destination)

            if os.path.isdir(destination):
                errors.append(BuildError(f"{i}.destination is a directory"))
                continue

            os.makedirs(os.path.dirname(destination), exist_ok=True)

            try:
                res, _ = container.get_archive(source)
            except docker.errors.NotFound:
                errors.append(BuildError(f"file {source} not found in container"))
                continue

            with open(destination, "wb") as h:
                for chunk in res:
                    h.write(chunk)

        container.remove(force=True)

        return errors
