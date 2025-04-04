import math
import os.path
import typing

import docker.errors
import docker.models.images
import pydantic

from ...docker import to_docker_tag
from ...error import BuildError, DeployError, LibError, SkipError
from ...k8s.models import (
    K8sContainer,
    K8sContainerEnv,
    K8sContainerLivenessProbe,
    K8sContainerLivenessProbeExec,
    K8sContainerPort,
    K8sContainerResourceLimits,
    K8sContainerResourceRequests,
    K8sContainerResources,
    K8sDeployment,
    K8sDeploymentSpec,
    K8sKind,
    K8sList,
    K8sMatchSelector,
    K8sMetadata,
    K8sPodSpec,
    K8sPodTemplate,
    K8sService,
    K8sServicePort,
    K8sServiceSpec,
    K8sServiceType,
)
from ..arguments import ArgumentContext, Arguments
from ..healthcheck import Healthcheck
from ..path import FilePath, PathContext
from ..port import Port
from .base import BaseDeploy, DockerDeployContext, K8sDeployContext
from .cpu import CPU
from .memory import Memory


class DeployDocker(BaseDeploy):
    """
    Deployment using Docker.
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
    env: typing.List[Arguments] = pydantic.Field(
        default_factory=list,
        description="Environments for Dockerfile",
        discriminator="type",
    )
    ports: typing.List[Port] = pydantic.Field(
        default_factory=list, description="Ports for deployment", discriminator="type"
    )
    healthcheck: typing.Optional[Healthcheck] = pydantic.Field(
        default=None, description="Healtcheck for Dockerfile"
    )
    cpu: typing.Optional[CPU] = pydantic.Field(
        default=None, description="CPU configuration for container"
    )
    memory: typing.Optional[Memory] = pydantic.Field(
        default=None, description="Memory configuration for container"
    )

    def get_tag_name(
        self, context: typing.Union[DockerDeployContext, K8sDeployContext]
    ) -> str:
        return to_docker_tag(context.name)

    def get_full_tag_name(
        self, context: typing.Union[DockerDeployContext, K8sDeployContext]
    ) -> str:
        return to_docker_tag(context.name, context.repository)

    def get_container_name(
        self, context: typing.Union[DockerDeployContext, K8sDeployContext]
    ) -> str:
        if isinstance(context, DockerDeployContext) and context.network:
            return to_docker_tag(f"{context.network}-{context.name}")

        return self.get_tag_name(context)

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
        self, context: DockerDeployContext, dockerfile: str, tag: bool
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
                tag=self.get_full_tag_name(context) if tag else None,
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

        image, image_errors = self.__build_image(
            context=context, dockerfile=dockerfile, tag=context.tag
        )
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

        dns_name = self.get_tag_name(context)
        aliases.append(dns_name)

        container_name = self.get_container_name(context)
        if container_name != dns_name:
            aliases.append(container_name)

        cpu_min: typing.Optional[int] = None
        cpu_max: typing.Optional[int] = None
        if self.cpu:
            if self.cpu.min:
                t_min = 0.0

                if self.cpu.min.endswith("m"):
                    t_min = float(self.cpu.min[:-1]) / 1_000
                else:
                    t_min = float(self.cpu.min)

                cpu_min = int(t_min * 1024)

            if self.cpu.max:
                t_max: float = 0.0

                if self.cpu.max.endswith("m"):
                    t_max = float(self.cpu.max[:-1]) / 1_000
                else:
                    t_max = float(self.cpu.max)

                cpu_max = int(t_max * 1e9)

        mem_min: typing.Optional[str] = None
        mem_max: typing.Optional[str] = None
        if self.memory:
            mem_min = (self.memory.min or "").lower()
            mem_max = (self.memory.max or "").lower()

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
                cpu_shares=cpu_min,
                nano_cpus=cpu_max,
                mem_reservation=mem_min,
                mem_limit=mem_max,
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

        image, image_errors = self.__build_image(
            context=context, dockerfile=dockerfile, tag=context.tag
        )
        if not image:
            return image_errors

        return []

    def k8s_build(
        self, context: K8sDeployContext
    ) -> typing.Tuple[typing.Optional[K8sList], typing.Sequence[LibError]]:
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

        if errors:
            return None, errors

        labels = {
            "type": "challenge",
            "track": to_docker_tag(context.track),
            "challenge": self.get_tag_name(context),
        }

        container = K8sContainer(
            name=self.get_tag_name(context),
            image=self.get_full_tag_name(context),
            imagePullPolicy=context.image_pull_policy,
            ports=[
                K8sContainerPort(
                    name=(
                        f"p-{next(context.port_generator)}"
                        if port.public
                        else f"p-{port.value}"
                    ),
                    containerPort=port.value,
                )
                for port in self.ports
            ],
            env=[
                K8sContainerEnv(name=key, value=value)
                for key, value in environment.items()
            ],
            livenessProbe=(
                K8sContainerLivenessProbe(
                    exec=K8sContainerLivenessProbeExec(
                        command=["/bin/sh", "-c", self.healthcheck.test]
                    ),
                    initialDelaySeconds=math.ceil(self.healthcheck.start_period),
                    periodSeconds=math.ceil(self.healthcheck.interval),
                    successThreshold=1,
                    failureThreshold=self.healthcheck.retries,
                )
                if self.healthcheck
                else None
            ),
            resources=(
                K8sContainerResources(
                    requests=(
                        K8sContainerResourceRequests(
                            cpu=self.cpu.min if self.cpu else None,
                            memory=self.memory.min if self.memory else None,
                        )
                        if (self.cpu and self.cpu.min)
                        or (self.memory and self.memory.min)
                        else None
                    ),
                    limits=(
                        K8sContainerResourceLimits(
                            cpu=self.cpu.max if self.cpu else None,
                            memory=self.memory.max if self.memory else None,
                        )
                        if (self.cpu and self.cpu.max)
                        or (self.memory and self.memory.max)
                        else None
                    ),
                )
                if self.cpu or self.memory
                else None
            ),
        )

        items: typing.List[K8sKind] = []

        deployment = K8sDeployment(
            apiVersion="apps/v1",
            kind="Deployment",
            metadata=K8sMetadata(name=self.get_tag_name(context), labels=labels),
            spec=K8sDeploymentSpec(
                replicas=1,
                selector=K8sMatchSelector(
                    matchLabels={"challenge": self.get_tag_name(context)}
                ),
                template=K8sPodTemplate(
                    metadata=K8sMetadata(
                        name=self.get_tag_name(context), labels=labels
                    ),
                    spec=K8sPodSpec(containers=[container]),
                ),
            ),
        )
        items.append(deployment)

        if self.ports:
            service = K8sService(
                apiVersion="v1",
                kind="Service",
                metadata=K8sMetadata(name=self.get_tag_name(context), labels=labels),
                spec=K8sServiceSpec(
                    type=K8sServiceType.ClusterIP,
                    selector={"challenge": self.get_tag_name(context)},
                    ports=[
                        K8sServicePort(
                            name=f"p-{port.value}",
                            protocol=port.k8s_port_protocol(),
                            port=port.value,
                            targetPort=port.value,
                        )
                        for port in self.ports
                    ],
                ),
            )
            items.append(service)

        out = K8sList(
            apiVersion="v1",
            kind="List",
            metadata=K8sMetadata(),
            items=items,
        )

        return out, []
