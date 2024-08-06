import abc
import dataclasses
import os.path
import typing

import docker
import docker.errors
import docker.types

from ..error import BuildError, DeployError, LibError, SkipError
from ..schema import Deployer, DeployerDocker, PortProtocol

from .args import BuildArgs
from .utils import subclass_get, to_docker_tag


def default_port_generator() -> typing.Generator[typing.Optional[str], None, None]:
    while True:
        yield None


@dataclasses.dataclass
class DeployContext:
    name: str
    path: str
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )
    network: typing.Optional[str] = dataclasses.field(default=None)
    host: typing.Optional[str] = dataclasses.field(default=None)
    port_generator: typing.Generator[typing.Optional[str], None, None] = (
        dataclasses.field(default_factory=lambda: default_port_generator())
    )


class BuildDeployer(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Deployer]:
        return None

    @classmethod
    def get(cls, obj: Deployer) -> typing.Type["BuildDeployer"]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def has_host(cls, deployer: DeployerDocker) -> bool:
        return False

    @classmethod
    @abc.abstractmethod
    def public_ports(
        cls, deployer: DeployerDocker
    ) -> typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]:
        return []

    @classmethod
    @abc.abstractmethod
    def deploy_ports(
        cls, deployer: DeployerDocker, port: int
    ) -> typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]:
        return []

    @classmethod
    @abc.abstractmethod
    def is_active(cls, context: DeployContext, deployer: Deployer) -> bool:
        return False

    @classmethod
    @abc.abstractmethod
    def start(
        cls, context: DeployContext, deployer: Deployer, skip_reuse: bool = True
    ) -> typing.Sequence[LibError]:
        return []

    @classmethod
    @abc.abstractmethod
    def stop(
        cls, context: DeployContext, deployer: Deployer
    ) -> typing.Sequence[LibError]:
        return []


class BuildDeployerDocker(BuildDeployer):
    @classmethod
    def __type__(cls) -> typing.Type[Deployer]:
        return DeployerDocker

    @classmethod
    def get_name(cls, context: DeployContext) -> str:
        return to_docker_tag(context.name)

    @classmethod
    def has_host(cls, deployer: DeployerDocker) -> bool:
        return any(port.public for port in deployer.ports)

    @classmethod
    def public_ports(
        cls, deployer: DeployerDocker
    ) -> typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]:
        return [
            (port.protocol, port.port) if port.public else None
            for port in deployer.ports
        ]

    @classmethod
    def deploy_ports(
        cls, deployer: DeployerDocker, port: int
    ) -> typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]:
        out = []
        for p in deployer.ports:
            if p.public:
                v = port
                port += 1
            else:
                v = None

            out.append((p.protocol, v))

        return out

    @classmethod
    def is_active(cls, context: DeployContext, deployer: DeployerDocker) -> bool:
        if context.docker_client is None:
            return False

        try:
            container = context.docker_client.containers.get(cls.get_name(context))
        except:
            return False

        return container.status == "running" and container.health in (
            "unknown",
            "healthy",
        )

    @classmethod
    def start(
        cls, context: DeployContext, deployer: DeployerDocker, skip_reuse: bool = True
    ) -> typing.Sequence[LibError]:
        if context.docker_client is None:
            return [BuildError(context="Docker", msg="client not initialized")]

        if deployer.path is None:
            dockerfile = os.path.join(context.path, "Dockerfile")
        else:
            dockerfile = deployer.path.resolve(context.path)

        if dockerfile is None or not os.path.isfile(dockerfile):
            return [BuildError(context="Dockerfile", msg="is not a file")]

        dockerfile = os.path.abspath(dockerfile)

        errors = []
        build_args = {}
        for args in deployer.args:
            if (arg_map := BuildArgs.get(args).build(context.path, args)) is None:
                errors.append(
                    BuildError(context=context.name, msg="invalid build args")
                )
                break

            for key, value in arg_map.items():
                build_args[key] = value

        environment = {}
        for env in deployer.env:
            if (arg_map := BuildArgs.get(env).build(context.path, env)) is None:
                errors.append(
                    BuildError(context=context.name, msg="invalid environment")
                )
                break

            for key, value in arg_map.items():
                environment[key] = value

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

        port_bindings = {}
        for port in deployer.ports:
            if not port.public:
                continue

            if context.host:
                port_bindings[port.port] = (context.host, next(context.port_generator))

        if errors:
            return errors

        aliases = [cls.get_name(context)]
        if deployer.name:
            aliases += [to_docker_tag(deployer.name)]

        try:
            context.docker_client.containers.run(
                image=image,
                detach=True,
                name=cls.get_name(context),
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
                        "test": deployer.healthcheck.test,
                        "interval": int(deployer.healthcheck.interval * 1_000_000_000),
                        "timeout": int(deployer.healthcheck.timeout * 1_000_000_000),
                        "retries": deployer.healthcheck.retries,
                        "start_period": int(
                            deployer.healthcheck.start_period * 1_000_000_000
                        ),
                    }
                    if deployer.healthcheck
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
                        DeployError(context=context.name, msg="failed to deploy due to duplicate container", error=e)
                    )
            else:
                errors.append(
                    DeployError(context=context.name, msg="failed to deploy", error=e)
                )

        return errors

    @classmethod
    def stop(
        cls, context: DeployContext, deployer: Deployer
    ) -> typing.Sequence[LibError]:
        name = to_docker_tag(context.name)

        try:
            container = context.docker_client.containers.get(name)

            container.remove(force=True)
        except docker.errors.NotFound:
            return [SkipError()]
        except docker.errors.APIError as e:
            [DeployError(context=context.name, msg="failed to deploy", error=e)]

        return []
