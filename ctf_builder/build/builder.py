import abc
import dataclasses
import io
import os.path
import tarfile
import typing

import docker
import docker.errors

from ..error import BuildError, LibError
from ..schema import Builder, BuilderDocker

from .args import BuildArgs
from .file_map import BuildFileMap
from .utils import subclass_get

T = typing.TypeVar("T", bound=Builder)


@dataclasses.dataclass
class BuildContext:
    path: str
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


class BuildBuilder(typing.Generic[T], abc.ABC):
    @classmethod
    def get(cls, obj: T) -> typing.Type["BuildBuilder"]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(cls, context: BuildContext, builder: T) -> typing.Sequence[LibError]:
        pass


class BuildBuilderDocker(BuildBuilder[BuilderDocker]):
    @classmethod
    def build(
        cls, context: BuildContext, builder: BuilderDocker
    ) -> typing.Sequence[LibError]:
        if context.docker_client is None:
            return [BuildError(context="Docker", msg="no client initialized")]

        dockerfile: typing.Optional[str]
        if builder.path is None:
            dockerfile = os.path.join(context.path, "Dockerfile")
        else:
            dockerfile = builder.path.resolve(context.path)

        if dockerfile is None or not os.path.isfile(dockerfile):
            return [BuildError(context="Dockerfile", msg="is not a file")]

        dockerfile = os.path.abspath(dockerfile)

        errors = []
        build_args = {}
        for args in builder.args:
            if (arg_map := BuildArgs.get(args).build(context.path, args)) is None:
                errors.append(
                    BuildError(context="Dockerfile", msg="invalid build args")
                )
                break

            for key, value in arg_map.items():
                build_args[key] = value

        try:
            image, logs = context.docker_client.images.build(
                path=os.path.dirname(dockerfile),
                dockerfile=dockerfile,
                buildargs=build_args,
            )
        except docker.errors.BuildError as e:
            return errors + [
                BuildError(context="Dockerfile", msg="failed to build", error=e)
            ]

        try:
            container = context.docker_client.containers.create(image=image)
        except docker.errors.APIError as e:
            return errors + [
                BuildError(context="Dockerfile", msg="failed to create", error=e)
            ]

        try:
            for file_map in builder.files:
                source, destination = BuildFileMap.build(file_map)
                destination = os.path.join(os.path.abspath(context.path), destination)

                if os.path.isdir(destination):
                    errors.append(BuildError(context=destination, msg="is a directory"))
                    continue

                os.makedirs(os.path.dirname(destination), exist_ok=True)

                try:
                    res, _ = container.get_archive(source)
                except docker.errors.NotFound:
                    errors.append(
                        BuildError(context=source, msg="was not found in container")
                    )
                    continue

                tar_data = io.BytesIO()
                for chunk in res:
                    tar_data.write(chunk)
                tar_data.seek(0)

                with tarfile.TarFile.open(fileobj=tar_data, mode="r") as th:
                    members = th.getmembers()
                    if len(members) != 1:
                        errors.append(
                            BuildError(
                                context=source, msg="is a directory in the container"
                            )
                        )
                        continue

                    extract_file = th.extractfile(members[0])
                    if extract_file is None:
                        errors.append(
                            BuildError(context=source, msg="file cannot be extracted")
                        )
                        continue

                    with open(destination, "wb") as dh:
                        dh.write(extract_file.read())
        finally:
            try:
                container.remove(force=True)
            except:
                pass

        return errors
