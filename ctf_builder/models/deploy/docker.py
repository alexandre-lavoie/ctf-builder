import os.path
import typing

import docker.errors
import docker.models.images
import pydantic

from ...docker import to_docker_tag
from ...error import BuildError, DeployError, LibError, SkipError
from ..arguments import ArgumentContext, Arguments
from ..healthcheck import Healthcheck
from ..path import FilePath, PathContext
from ..port import Port
from .base import BaseDeploy, DockerDeployContext


class DeployDocker(BaseDeploy):
    """
    Deployment using Docker.
    """

    type: typing.Literal["docker"]
    name: typing.Optional[str] = pydantic.Field(
        default=None, description="Hostname on network"
    )
    path: typing.Optional[FilePath] = pydantic.Field(
        default=None, description="Path to Dockerfile"
    )
    args: typing.List[Arguments] = pydantic.Field(
        default_factory=list,
        description="Build arguments for Dockerfile",
        discriminator="type",
    )
    env: typing.List[Arguments] = pydantic.Field(
        default_factory=list,
        description="Environments for Dockerfile",
        discriminator="type",
    )
    ports: typing.List[Port] = pydantic.Field(
        default_factory=list, description="Ports for deployment", discriminator="type"
    )
    healthcheck: typing.Optional[Healthcheck] = pydantic.Field(
        default=None, description=("Healtcheck for Dockerfile")
    )

    def get_dns_name(self, context: DockerDeployContext) -> str:
        return to_docker_tag(context.name)

    def get_container_name(self, context: DockerDeployContext) -> str:
        if context.network:
            return to_docker_tag(f"{context.network}_{context.name}")

        return self.get_dns_name(context)

    def get_ports(self) -> typing.Sequence[Port]:
        return self.ports

    def has_healthcheck(self) -> bool:
        return self.healthcheck is not None

    def docker_healthcheck(self, context: DockerDeployContext) -> bool:
        if context.docker_client is None:
            return False

        try:
            container = context.docker_client.containers.get(
                self.get_container_name(context)
            )
        except:
            return False

        status: str = container.status
        health: str = container.health

        return status == "running" and health == "healthy"

    def __dockerfile(
        self, context: DockerDeployContext
    ) -> typing.Tuple[typing.Optional[str], typing.Sequence[LibError]]:
        if context.docker_client is None:
            return None, [BuildError(context="Docker", msg="client not initialized")]

        dockerfile: typing.Optional[str]
        if self.path is None:
            dockerfile = os.path.join(context.root, "Dockerfile")
        else:
            dockerfile = self.path.resolve(PathContext(root=context.root))

        if dockerfile is None or not os.path.isfile(dockerfile):
            return None, [BuildError(context="Dockerfile", msg="is not a file")]

        return os.path.abspath(dockerfile), []

    def __build_image(
        self, context: DockerDeployContext, dockerfile: str
    ) -> typing.Tuple[
        typing.Optional[docker.models.images.Image], typing.Sequence[LibError]
    ]:
        if context.docker_client is None:
            return None, [BuildError(context="Docker", msg="client not initialized")]

        errors: typing.List[LibError] = []

        build_args = {}
        for args in self.args:
            if (arg_map := args.build(ArgumentContext(root=context.root))) is None:
                errors.append(
                    BuildError(context=context.name, msg="invalid build args")
                )
                break

            for key, value in arg_map.items():
                build_args[key] = value

        if errors:
            return None, errors

        try:
            image, _ = context.docker_client.images.build(
                path=os.path.dirname(dockerfile),
                dockerfile=dockerfile,
                buildargs=build_args,
            )
        except docker.errors.BuildError as e:
            return None, [
                BuildError(context="Dockerfile", msg="failed to build", error=e)
            ]

        return image, []

    def docker_start(
        self, context: DockerDeployContext, skip_reuse: bool = True
    ) -> typing.Sequence[LibError]:
        dockerfile, docker_errors = self.__dockerfile(context)
        if context.docker_client is None or not dockerfile:
            return docker_errors

        image, image_errors = self.__build_image(context, dockerfile)
        if not image:
            return image_errors

        errors: typing.List[LibError] = []

        environment = {}
        for env in self.env:
            if (arg_map := env.build(ArgumentContext(root=context.root))) is None:
                errors.append(
                    BuildError(context=context.name, msg="invalid environment")
                )
                break

            for key, value in arg_map.items():
                environment[key] = value

        port_bindings = {}
        if context.host:
            for port in self.ports:
                if not port.public:
                    continue

                port_bindings[port.value] = (context.host, next(context.port_generator))

        if errors:
            return errors

        aliases = []

        dns_name = self.get_dns_name(context)
        aliases.append(dns_name)

        container_name = self.get_container_name(context)
        if container_name != dns_name:
            aliases.append(container_name)

        if self.name:
            aliases.append(to_docker_tag(self.name))

        try:
            context.docker_client.containers.run(
                image=image,
                detach=True,
                name=container_name,
                environment=environment,
                ports=port_bindings,
                network=context.network,
                networking_config={
                    context.network: context.docker_client.api.create_endpoint_config(
                        aliases=aliases
                    )
                },
                healthcheck=(
                    {
                        "test": self.healthcheck.test,
                        "interval": int(self.healthcheck.interval * 1_000_000_000),
                        "timeout": int(self.healthcheck.timeout * 1_000_000_000),
                        "retries": self.healthcheck.retries,
                        "start_period": int(
                            self.healthcheck.start_period * 1_000_000_000
                        ),
                    }
                    if self.healthcheck
                    else None
                ),
            )

            return []
        except docker.errors.ImageNotFound:
            errors.append(DeployError(context=context.name, msg="image not found"))
        except docker.errors.APIError as e:
            if "reuse that name" in str(e):
                if skip_reuse:
                    errors.append(SkipError())
                else:
                    errors.append(
                        DeployError(
                            context=context.name,
                            msg="failed to deploy due to duplicate container",
                            error=e,
                        )
                    )
            else:
                errors.append(
                    DeployError(context=context.name, msg="failed to deploy", error=e)
                )

        return errors

    def docker_stop(
        self, context: DockerDeployContext, skip_not_found: bool = True
    ) -> typing.Sequence[LibError]:
        if context.docker_client is None:
            return [BuildError(context="Docker", msg="client not initialized")]

        try:
            container = context.docker_client.containers.get(
                self.get_container_name(context)
            )

            container.remove(force=True)
        except docker.errors.NotFound:
            if skip_not_found:
                return [SkipError()]
            else:
                return [DeployError(context=context.name, msg="failed to stop")]
        except docker.errors.APIError as e:
            [DeployError(context=context.name, msg="failed to stop", error=e)]

        return []

    def docker_deploy(self, context: DockerDeployContext) -> typing.Sequence[LibError]:
        dockerfile, docker_errors = self.__dockerfile(context)
        if not dockerfile:
            return docker_errors

        image, image_errors = self.__build_image(context, dockerfile)
        if not image:
            return image_errors

        return []
