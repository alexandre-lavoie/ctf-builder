import abc
import dataclasses
import os.path
import threading
import typing

import docker
import docker.errors
import docker.models.containers

from ..error import TestError, BuildError, LibError
from ..schema import Tester, TesterDocker, Challenge, Deployer

from .args import BuildArgs
from .deployer import BuildDeployer
from .flag import BuildFlag
from .utils import subclass_get


@dataclasses.dataclass
class TestContext:
    path: str
    challenges: typing.Sequence[Challenge]
    deployers: typing.Sequence[Deployer]
    network: typing.Optional[str]
    docker_client: typing.Optional[docker.DockerClient] = dataclasses.field(
        default=None
    )


class BuildTester(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Tester]:
        return None

    @classmethod
    def get(cls, obj: Tester) -> typing.Type["BuildTester"]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(cls, context: TestContext, tester: Tester) -> typing.Sequence[LibError]:
        return []


@dataclasses.dataclass(frozen=True)
class DockerTestContext:
    docker_client: docker.DockerClient
    image: str
    network: str
    environment: typing.Mapping[str, str]
    challenge_id: int
    challenge_host: typing.Optional[str]
    challenge_port: typing.Optional[int]
    flag: str
    flag_type: str
    errors: typing.List[TestError]


def docker_test(context: DockerTestContext):
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
            remove=True
        )
    except docker.errors.ContainerError as e:
        stderr: bytes = e.stderr if e.stderr else b""

        fail_offset = stderr.find(b"FAIL: ")

        if fail_offset >= 0:
            error = TestError(
                context=f"Challenge {context.challenge_id}",
                expected=context.flag,
                actual=stderr[fail_offset + 6:].decode()
            )
        else:
            error = TestError(
                context=f"Challenge {context.challenge_id}",
                expected=context.flag,
                error=ValueError(stderr.decode())
            )
    except Exception as e:
        error = TestError(
            context=f"Challenge {context.challenge_id}",
            expected=context.flag,
            error=e
        )

    if error:
        context.errors.append(error)


class BuildTesterDocker(BuildTester):
    @classmethod
    def __type__(cls) -> typing.Type[Tester]:
        return TesterDocker

    @classmethod
    def build(
        cls, context: TestContext, tester: TesterDocker
    ) -> typing.Sequence[LibError]:
        if context.docker_client is None:
            return [BuildError(
                context="Docker",
                msg="no client initialized")]

        if tester.path is None:
            dockerfile = os.path.join(context.path, "Dockerfile")
        else:
            dockerfile = tester.path.resolve(context.path)

        if dockerfile is None or not os.path.isfile(dockerfile):
            return [BuildError(
                context="Dockerfile",
                msg="is not a file")]

        dockerfile = os.path.abspath(dockerfile)

        errors = []

        build_args = {}
        for args in tester.args:
            if (arg_map := BuildArgs.get(args).build(context.path, args)) is None:
                errors.append(BuildError(
                    context="Dockerfile",
                    msg="invalid build args"
                ))
                break

            for key, value in arg_map.items():
                build_args[key] = value

        environment = {}
        for env in tester.env:
            if (arg_map := BuildArgs.get(env).build(context.path, env)) is None:
                errors.append(BuildError(
                    context="Dockerfile",
                    msg="invalid environment"
                ))
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
            return errors + [BuildError(
                context="Dockerfile",
                msg="failed to build",
                error=e
            )]

        if tester.challenges:
            challenges = {}

            for challenge_id in tester.challenges:
                if challenge_id < 0 or challenge_id >= len(context.challenges):
                    errors.append(BuildError(
                        context=f"Challenge {challenge_id}",
                        msg="invalid id"
                    ))
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
                    errors.append(BuildError(
                        context=f"Challenge {challenge_id}",
                        msg="invalid host"
                    ))
                    continue

                challenge_host = f"{context.network}_{challenge.host.index}"

                deployer = context.deployers[challenge.host.index]

                for data in BuildDeployer.get(deployer).public_ports(deployer):
                    if data is None:
                        continue

                    _, challenge_port = data
                    break
                else:
                    challenge_port = None
            else:
                challenge_host = None
                challenge_port = None

            for flag_def in challenge.flags:
                for flag in BuildFlag.build(context.path, flag_def):
                    test_context = DockerTestContext(
                        docker_client=context.docker_client,
                        image=image.id,
                        network=context.network,
                        environment=environment,
                        challenge_id=challenge_id,
                        challenge_host=challenge_host,
                        challenge_port=challenge_port,
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
