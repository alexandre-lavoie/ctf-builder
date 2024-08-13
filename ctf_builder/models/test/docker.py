import dataclasses
import os.path
import threading
import typing

import docker
import docker.errors
import pydantic

from ...docker import to_docker_tag
from ...error import BuildError, LibError, TestError
from ..arguments import ArgumentContext, Arguments
from ..flag import FlagContext
from ..path import FilePath, PathContext
from .base import BaseTest, TestContext


@dataclasses.dataclass(frozen=True)
class DockerTestContext:
    docker_client: docker.DockerClient
    image: str
    network: typing.Optional[str]
    environment: typing.Mapping[str, str]
    challenge_id: int
    challenge_host: typing.Optional[str]
    challenge_port: typing.Optional[int]
    flag: str
    flag_type: str
    errors: typing.List[TestError]


def docker_test(context: DockerTestContext) -> None:
    error = None
    try:
        context.docker_client.containers.run(
            image=context.image,
            network=context.network,
            environment={
                **context.environment,
                "CHALLENGE_ID": context.challenge_id,
                "CHALLENGE_HOST": context.challenge_host,
                "CHALLENGE_PORT": context.challenge_port,
                "FLAG": context.flag,
                "FLAG_TYPE": context.flag_type,
            },
            remove=True,
        )
    except docker.errors.ContainerError as e:
        stderr: bytes = e.stderr if e.stderr else b""

        fail_offset = stderr.find(b"FAIL: ")

        if fail_offset >= 0:
            error = TestError(
                context=f"Challenge {context.challenge_id}",
                expected=context.flag,
                actual=stderr[fail_offset + 6 :].decode(),
            )
        else:
            error = TestError(
                context=f"Challenge {context.challenge_id}",
                expected=context.flag,
                error=ValueError(stderr.decode()),
            )
    except Exception as e:
        error = TestError(
            context=f"Challenge {context.challenge_id}", expected=context.flag, error=e
        )

    if error:
        context.errors.append(error)


class TestDocker(BaseTest):
    """
    Testing using Dockerfile.
    """

    type: typing.Literal["docker"]
    challenges: typing.List[int] = pydantic.Field(
        default_factory=list,
        description="Challenges to run test on, all by default",
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

    def build(self, context: TestContext) -> typing.Sequence[LibError]:
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

        errors: typing.List[LibError] = []

        build_args = {}
        for args in self.args:
            if (arg_map := args.build(ArgumentContext(root=context.root))) is None:
                errors.append(
                    BuildError(context="Dockerfile", msg="invalid build args")
                )
                break

            for key, value in arg_map.items():
                build_args[key] = value

        environment = {}
        for env in self.env:
            if (arg_map := env.build(ArgumentContext(root=context.root))) is None:
                errors.append(
                    BuildError(context="Dockerfile", msg="invalid environment")
                )
                break

            for key, value in arg_map.items():
                environment[key] = value

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

        if self.challenges:
            challenges = {}

            for challenge_id in self.challenges:
                if challenge_id < 0 or challenge_id >= len(context.challenges):
                    errors.append(
                        BuildError(
                            context=f"Challenge {challenge_id}", msg="invalid id"
                        )
                    )
                    continue

                challenges[challenge_id] = context.challenges[challenge_id]

            if errors:
                return errors
        else:
            challenges = {i: c for i, c in enumerate(context.challenges)}

        test_threads: typing.List[typing.Tuple[threading.Thread, DockerTestContext]] = (
            []
        )
        for challenge_id, challenge in challenges.items():
            if challenge.host:
                if challenge.host.index < 0 or challenge.host.index > len(
                    context.deployers
                ):
                    errors.append(
                        BuildError(
                            context=f"Challenge {challenge_id}", msg="invalid host"
                        )
                    )
                    continue

                challenge_host = to_docker_tag(f"{context.name}-{challenge.host.index}")

                deployer = context.deployers[challenge.host.index]

                if not (ports := deployer.get_ports()):
                    errors.append(
                        BuildError(
                            context=f"Challenge {challenge_id}", msg="no exposed ports"
                        )
                    )
                    continue

                challenge_port = ports[0]
            else:
                challenge_host = None
                challenge_port = None

            for flag_def in challenge.flags:
                for flag in flag_def.build(FlagContext(root=context.root)):
                    test_context = DockerTestContext(
                        docker_client=context.docker_client,
                        image=image.id,
                        network=context.network,
                        environment=environment,
                        challenge_id=challenge_id,
                        challenge_host=challenge_host,
                        challenge_port=challenge_port.value if challenge_port else None,
                        flag=flag,
                        flag_type="regex" if flag_def.regex else "static",
                        errors=[],
                    )

                    test_threads.append(
                        (
                            threading.Thread(target=docker_test, args=(test_context,)),
                            test_context,
                        )
                    )

        for thread, _ in test_threads:
            thread.start()

        for thread, _ in test_threads:
            thread.join()

        for _, test_context in test_threads:
            errors += test_context.errors

        return errors
