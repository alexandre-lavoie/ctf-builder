import os.path
import io
import typing
import tarfile

import docker
import docker.errors
import docker.models.containers
import pydantic

from .base import BuildContext, BaseBuild
from ...error import LibError, BuildError

from ..arguments import Arguments, ArgumentContext
from ..file import FileMap
from ..path import FilePath, PathContext


class BuildDocker(BaseBuild):
    """
    Builder using Dockerfiles.
    """

    type: typing.Literal["docker"]
    path: typing.Optional[FilePath] = pydantic.Field(
        default=None, description="Path to Dockerfile"
    )
    args: typing.List[Arguments] = pydantic.Field(
        default_factory=list,
        description="Build arguments for Dockerfile",
        discriminator="type",
    )
    files: typing.List[FileMap] = pydantic.Field(
        default_factory=list, description="Files to map after build"
    )

    def build(self, context: BuildContext) -> typing.Sequence[LibError]:
        if context.docker_client is None:
            return [BuildError(context="Docker", msg="no client initialized")]

        dockerfile: typing.Optional[str]
        if self.path is None:
            dockerfile = os.path.join(context.root, "Dockerfile")
        else:
            dockerfile = self.path.resolve(PathContext(root=context.root))

        if dockerfile is None or not os.path.isfile(dockerfile):
            return [BuildError(context="Dockerfile", msg="is not a file")]

        dockerfile = os.path.abspath(dockerfile)

        errors = []
        build_args = {}
        for args in self.args:
            if (arg_map := args.build(ArgumentContext(root=context.root))) is None:
                errors.append(
                    BuildError(context="Dockerfile", msg="invalid build args")
                )
                break

            for key, value in arg_map.items():
                build_args[key] = value

        try:
            image, _ = context.docker_client.images.build(
                path=os.path.dirname(dockerfile),
                dockerfile=dockerfile,
                buildargs=build_args,
            )
        except docker.errors.BuildError as e:
            return errors + [
                BuildError(context="Dockerfile", msg="failed to build", error=e)
            ]

        try:
            container: docker.models.containers.Container = (
                context.docker_client.containers.create(image=image)
            )
        except docker.errors.APIError as e:
            return errors + [
                BuildError(context="Dockerfile", msg="failed to create", error=e)
            ]

        try:
            for file_map in self.files:
                handle = file_map.build()
                destination = os.path.join(
                    os.path.abspath(context.root), handle.destination
                )

                if os.path.isdir(destination):
                    errors.append(BuildError(context=destination, msg="is a directory"))
                    continue

                os.makedirs(os.path.dirname(destination), exist_ok=True)

                try:
                    res, _ = container.get_archive(handle.source)
                except docker.errors.NotFound:
                    errors.append(
                        BuildError(
                            context=handle.source, msg="was not found in container"
                        )
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
                                context=handle.source,
                                msg="is a directory in the container",
                            )
                        )
                        continue

                    extract_file = th.extractfile(members[0])
                    if extract_file is None:
                        errors.append(
                            BuildError(
                                context=handle.source, msg="file cannot be extracted"
                            )
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
