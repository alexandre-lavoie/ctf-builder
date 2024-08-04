import abc
import dataclasses
import os.path
import typing

import docker
import docker.errors
import docker.types

from ..error import DeployError, LibError, SkipError
from ..logging import LOG
from ..schema import Deployer, DeployerDocker, PortProtocol

from .args import BuildArgs
from .utils import subclass_get

@dataclasses.dataclass
class DeployContext:
    name: str
    path: str
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(default=None)
    network: typing.Optional[str] = dataclasses.field(default=None)
    host: typing.Optional[str] = dataclasses.field(default=None)
    next_port: typing.Callable[[], typing.Optional[int]] = dataclasses.field(default_factory=lambda: lambda: None)

class BuildDeployer(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Deployer]:
        return None
    
    @classmethod
    def get(cls, obj: Deployer) -> typing.Optional[typing.Type["BuildDeployer"]]:
        return subclass_get(cls, obj)
    
    @classmethod
    @abc.abstractmethod
    def has_host(cls, deployer: DeployerDocker) -> bool:
        return False
    
    @classmethod
    @abc.abstractmethod
    def public_ports(cls, deployer: DeployerDocker, port: int) -> typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]:
        return []

    @classmethod
    @abc.abstractmethod
    def start(cls, context: DeployContext, deployer: Deployer) -> typing.Sequence[LibError]:
        return []
    
    @classmethod
    @abc.abstractmethod
    def stop(cls, context: DeployContext, deployer: Deployer) -> typing.Sequence[LibError]:
        return []

class BuildDeployerDocker(BuildDeployer):
    @classmethod
    def __type__(cls) -> typing.Type[Deployer]:
        return DeployerDocker
    
    @classmethod
    def get_name(cls, context: DeployContext) -> str:
        return cls.to_docker_tag(context.name)

    @classmethod
    def to_docker_tag(cls, text: str) -> str:
        return text.replace(" ", "_").lower()
    
    @classmethod
    def has_host(cls, deployer: DeployerDocker) -> bool:
        return any(port.public for port in deployer.ports)

    @classmethod
    def public_ports(cls, deployer: DeployerDocker, port: int) -> typing.Sequence[typing.Optional[typing.Tuple[PortProtocol, int]]]:
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
    def start(cls, context: DeployContext, deployer: DeployerDocker) -> typing.Sequence[LibError]:
        if context.docker_client is None:
            return [DeployError("No docker client")]

        if deployer.path is None:
            dockerfile = os.path.join(context.path, "Dockerfile")
        else:
            dockerfile = deployer.path.resolve(context.path)

        if dockerfile is None or not os.path.exists(dockerfile):
            return [DeployError("Dockerfile is invalid")]

        dockerfile = os.path.abspath(dockerfile)
        
        errors = []
        build_args = {}
        for args in deployer.args:
            ba = BuildArgs.get(args)
            if ba is None:
                errors.append(DeployError(f"unhandled {type(args)}"))
                continue

            arg_map = ba.build(context.path, args)
            if arg_map is None:
                errors.append(f"invalid {type(args)}")
                break 

            for key, value in arg_map.items():
                build_args[key] = value

        environment = {}
        for env in deployer.env:
            ba = BuildArgs.get(env)
            if ba is None:
                errors.append(DeployError(f"unhandled {type(env)}"))
                continue

            arg_map = ba.build(context.path, env)
            if arg_map is None:
                errors.append(f"invalid {type(env)}")
                break 

            for key, value in arg_map.items():
                environment[key] = value

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
            return errors + [DeployError(f"Dockerfile failed to build > {e}")]

        port_bindings = {}
        for port in deployer.ports:
            if not port.public:
                continue

            bind_port = context.next_port()

            if context.host:
                port_bindings[port.port] = (context.host, bind_port)

        if errors:
            return errors

        aliases = [cls.get_name(context)]
        if deployer.name:
            aliases += [cls.to_docker_tag(deployer.name)]

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
                }
            )

            return []
        except docker.errors.ImageNotFound:
            errors.append(DeployError("image not found for container"))
        except docker.errors.APIError as e:
            if "reuse that name" in str(e):
                errors.append(SkipError())
            else:
                errors.append(DeployError(f"api error when creating container > {e}"))

        return errors

    @classmethod
    def stop(cls, context: DeployContext, deployer: Deployer) -> typing.Sequence[LibError]:
        name = cls.to_docker_tag(context.name)

        try:
            container = context.docker_client.containers.get(name)

            container.remove(force=True)
        except docker.errors.NotFound:
            return [SkipError()]
        except docker.errors.APIError as e:
            [DeployError(f"api error when creating container > {e}")]

        return []
