import abc
import dataclasses
import io
import os.path
import tarfile
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
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


class BuildBuilder(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Builder]:
        return None

    @classmethod
    def get(cls, obj: Builder) -> typing.Type["BuildBuilder"]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(
        cls, context: BuildContext, builder: Builder
    ) -> typing.Sequence[BuildError]:
        return []


class BuildBuilderDocker(BuildBuilder):
    @classmethod
    def __type__(cls) -> typing.Type[Builder]:
        return BuilderDocker

    @classmethod
    def build(
        cls, context: BuildContext, builder: BuilderDocker
    ) -> typing.Sequence[BuildError]:
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
            if (arg_map := BuildArgs.get(args).build(context.path, args)) is None:
                errors.append("invalid build args")
                break

            for key, value in arg_map.items():
                build_args[key] = value

        try:
            image, logs = context.docker_client.images.build(
                path=os.path.dirname(dockerfile),
                dockerfile=dockerfile,
                buildargs=build_args,
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

        try:
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

                tar_data = io.BytesIO()
                for chunk in res:
                    tar_data.write(chunk)
                tar_data.seek(0)

                with tarfile.TarFile.open(fileobj=tar_data, mode="r") as th:
                    members = th.getmembers()
                    if len(members) != 1:
                        errors.append(BuildError("invalid tar file output"))
                        continue

                    with open(destination, "wb") as dh:
                        dh.write(th.extractfile(members[0]).read())
        finally:
            try:
                container.remove(force=True)
            except:
                pass

        return errors
