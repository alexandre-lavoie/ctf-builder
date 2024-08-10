import time
import typing

import docker
import docker.errors
import docker.models.containers

from ..error import DeployError, LibError


def ctfd_container(
    docker_client: docker.DockerClient, port: int, name: typing.Optional[str] = None
) -> typing.Tuple[
    typing.Optional[docker.models.containers.Container], typing.Sequence[LibError]
]:
    try:
        container: docker.models.containers.Container = docker_client.containers.run(
            name=name,
            image="ctfd/ctfd",
            ports={"8000": port},
            detach=True,
            remove=True,
            healthcheck={
                "test": "python -c \"import requests; requests.get('http://localhost:8000/')\" || exit 1",
                "interval": 1_000_000_000,
                "timeout": 1_000_000_000,
                "retries": 10,
                "start_period": 1_000_000_000,
            },
        )
    except Exception as e:
        return None, [DeployError(context="Container", msg="failed to deploy", error=e)]

    try:
        # Wait for container to be healthy
        for _ in range(40):
            container.reload()

            if container.health == "healthy":
                break

            time.sleep(0.5)
        else:
            raise Exception("Not healthy")
    except Exception as e:
        try:
            container.remove(force=True)
        except:
            pass

        return None, [
            DeployError(context="Container", msg="failed to become healthy", error=e)
        ]

    return container, []
