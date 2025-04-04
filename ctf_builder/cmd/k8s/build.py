import argparse
import dataclasses
import json
import os
import os.path
import typing

from ...config import CHALLENGE_BASE_PORT, CHALLENGE_MAX_PORTS
from ...docker import to_docker_tag
from ...error import LibError, SkipError
from ...k8s.models import (
    K8sConfigMap,
    K8sContainer,
    K8sContainerPort,
    K8sDeployment,
    K8sDeploymentSpec,
    K8sImagePullPolicy,
    K8sKeyPath,
    K8sList,
    K8sMatchSelector,
    K8sMetadata,
    K8sNetworkPolicy,
    K8sNetworkPolicyIngress,
    K8sNetworkPolicySelector,
    K8sNetworkPolicySpec,
    K8sNetworkPolicyType,
    K8sPodSpec,
    K8sPodTemplate,
    K8sPortProtocol,
    K8sService,
    K8sServicePort,
    K8sServiceSpec,
    K8sServiceType,
    K8sVolume,
    K8sVolumeConfigMap,
    K8sVolumeMount,
)
from ...models.challenge import Track
from ...models.deploy.base import K8sDeployContext
from ..common import (
    CliContext,
    WrapContext,
    cli_challenge_wrapper,
    get_challenge_index,
    get_challenges,
    port_generator,
)


@dataclasses.dataclass(frozen=True)
class Args:
    output: str
    pull: str = dataclasses.field(default="Always")
    challenge: typing.Sequence[str] = dataclasses.field(default_factory=list)
    repository: typing.Optional[str] = dataclasses.field(default=None)
    port: int = dataclasses.field(default=CHALLENGE_BASE_PORT)


@dataclasses.dataclass(frozen=True)
class PublicPort:
    host: str
    protocol: K8sPortProtocol
    public_port: int
    local_port: int


@dataclasses.dataclass(frozen=True)
class Context(WrapContext):
    output: str
    port: int
    public_ports: typing.List[PublicPort]
    repository: typing.Optional[str] = dataclasses.field(default=None)
    image_pull_policy: K8sImagePullPolicy = dataclasses.field(
        default=K8sImagePullPolicy.Always
    )


def cleanup(data: typing.Any) -> typing.Any:
    if isinstance(data, dict):
        delete_keys: typing.List[str] = []
        for k, v in data.items():
            if v is None:
                delete_keys.append(k)
            else:
                cleanup(v)

        for k in delete_keys:
            del data[k]
    elif isinstance(data, list):
        for v in data:
            cleanup(v)

    return data


def build(track: Track, context: Context) -> typing.Sequence[LibError]:
    if not track.deploy:
        return [SkipError()]

    path = os.path.join(
        context.output, "challenges", os.path.basename(context.challenge_path)
    )
    os.makedirs(path, exist_ok=True)

    next_port = port_generator(
        context.port + get_challenge_index(context.challenge_path) * CHALLENGE_MAX_PORTS
    )

    errors: typing.List[LibError] = []
    for i, deployer in enumerate(track.deploy):
        deploy_name = to_docker_tag(f"{track.tag or track.name}-{i}")

        k8s_obj, k8s_errors = deployer.k8s_build(
            K8sDeployContext(
                name=deploy_name,
                track=f"{track.tag or track.name}",
                root=context.challenge_path,
                port_generator=next_port,
                repository=context.repository,
                image_pull_policy=context.image_pull_policy,
            ),
        )
        if k8s_obj is None:
            errors += k8s_errors
            continue

        for item in k8s_obj.items:
            if not isinstance(item, K8sDeployment):
                continue

            for container in item.spec.template.spec.containers:
                for port_def, port in zip(deployer.get_ports(), container.ports):
                    if port_def.public:
                        context.public_ports.append(
                            PublicPort(
                                host=deploy_name,
                                protocol=port_def.k8s_port_protocol(),
                                public_port=int((port.name or "")[2:]),
                                local_port=port.containerPort,
                            )
                        )

        with open(os.path.join(path, f"{i}.json"), "w") as h:
            json.dump(cleanup(k8s_obj.model_dump(mode="json")), h, indent=2)

    if errors:
        return errors

    track_name = to_docker_tag(f"{track.tag or track.name}")

    network_policy = K8sNetworkPolicy(
        apiVersion="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=K8sMetadata(name=f"allow-{track_name}"),
        spec=K8sNetworkPolicySpec(
            podSelector=K8sMatchSelector(matchLabels={"track": track_name}),
            policyTypes=[K8sNetworkPolicyType.Ingress],
            ingress=[
                K8sNetworkPolicyIngress(
                    ports=None,
                    **{
                        "from": [
                            K8sNetworkPolicySelector(
                                podSelector=K8sMatchSelector(
                                    matchLabels={"track": track_name}
                                )
                            )
                        ]
                    },
                )
            ],
        ),
    )

    network_out = K8sList(
        apiVersion="v1", kind="List", metadata=K8sMetadata(), items=[network_policy]
    )

    with open(os.path.join(path, "network.json"), "w") as h:
        json.dump(
            cleanup(network_out.model_dump(mode="json", by_alias=True)), h, indent=2
        )

    return errors


def build_root(output: str, public_ports: typing.List[PublicPort]) -> bool:
    path = os.path.join(output, "challenges")

    network_policy = K8sNetworkPolicy(
        apiVersion="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=K8sMetadata(name="deny-challenges"),
        spec=K8sNetworkPolicySpec(
            podSelector=K8sMatchSelector(matchLabels={"type": "challenge"}),
            policyTypes=[K8sNetworkPolicyType.Ingress],
        ),
    )

    network_out = K8sList(
        apiVersion="v1", kind="List", metadata=K8sMetadata(), items=[network_policy]
    )

    with open(os.path.join(path, "network.json"), "w") as h:
        json.dump(
            cleanup(network_out.model_dump(mode="json", by_alias=True)), h, indent=2
        )

    load_balancer = K8sService(
        apiVersion="v1",
        kind="Service",
        metadata=K8sMetadata(name="load-balancer"),
        spec=K8sServiceSpec(
            type=K8sServiceType.LoadBalancer,
            selector={"type": "proxy"},
            ports=[
                K8sServicePort(
                    name=f"p-{public_port.public_port}",
                    protocol=public_port.protocol,
                    port=public_port.public_port,
                    targetPort=public_port.public_port,
                )
                for public_port in public_ports
            ],
        ),
    )

    nginx_config = K8sConfigMap(
        apiVersion="v1",
        kind="ConfigMap",
        metadata=K8sMetadata(name="nginx-conf"),
        data={
            "nginx.conf": "events {} stream { "
            + " ".join(
                f"server {{ listen {public_port.public_port}{' udp' if public_port.protocol is K8sPortProtocol.UDP else ''}; proxy_pass {public_port.host}:{public_port.local_port}; }}"
                for public_port in public_ports
            )
            + " }"
        },
    )

    proxy = K8sDeployment(
        apiVersion="apps/v1",
        kind="Deployment",
        metadata=K8sMetadata(name="proxy", labels={"type": "proxy"}),
        spec=K8sDeploymentSpec(
            replicas=1,
            selector=K8sMatchSelector(matchLabels={"type": "proxy"}),
            template=K8sPodTemplate(
                metadata=K8sMetadata(name="proxy", labels={"type": "proxy"}),
                spec=K8sPodSpec(
                    containers=[
                        K8sContainer(
                            name="nginx",
                            image="nginx:latest",
                            ports=[
                                K8sContainerPort(
                                    name=f"p-{public_port.public_port}",
                                    containerPort=public_port.public_port,
                                )
                                for public_port in public_ports
                            ],
                            volumeMounts=[
                                K8sVolumeMount(
                                    name="nginx-conf",
                                    mountPath="/etc/nginx/nginx.conf",
                                    subPath="nginx.conf",
                                    readOnly=True,
                                )
                            ],
                        )
                    ],
                    volumes=[
                        K8sVolume(
                            name="nginx-conf",
                            configMap=K8sVolumeConfigMap(
                                name="nginx-conf",
                                items=[K8sKeyPath(key="nginx.conf", path="nginx.conf")],
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    proxy_ingress: typing.Any = {
        "from": [
            K8sNetworkPolicySelector(
                podSelector=K8sMatchSelector(matchLabels={"type": "proxy"})
            )
        ],
    }

    proxy_network_policy = K8sNetworkPolicy(
        apiVersion="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=K8sMetadata(name="allow-proxy"),
        spec=K8sNetworkPolicySpec(
            podSelector=K8sMatchSelector(matchLabels={"type": "challenge"}),
            policyTypes=[K8sNetworkPolicyType.Ingress],
            ingress=[K8sNetworkPolicyIngress(**proxy_ingress)],
        ),
    )

    service_out = K8sList(
        apiVersion="v1",
        kind="List",
        metadata=K8sMetadata(),
        items=[load_balancer, nginx_config, proxy, proxy_network_policy],
    )

    with open(os.path.join(path, "service.json"), "w") as h:
        json.dump(
            cleanup(service_out.model_dump(mode="json", by_alias=True)), h, indent=2
        )

    return True


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-c",
        "--challenge",
        action="append",
        choices=get_challenges(root_directory) or [],
        help="Name of challenges",
        default=[],
    )
    parser.add_argument(
        "-r",
        "--repository",
        help="Container repository path for challenges",
        default=None,
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Starting port for challenges",
        default=CHALLENGE_BASE_PORT,
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory for files",
        default=os.path.join(root_directory, "k8s"),
    )
    parser.add_argument(
        "-u",
        "--pull",
        help="Image pull policy",
        choices=([e.value for e in K8sImagePullPolicy]),
        default=K8sImagePullPolicy.Always.value,
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    context = Context(
        challenge_path="",
        error_prefix=[],
        skip_inactive=False,
        output=args.output,
        port=args.port,
        public_ports=[],
        repository=args.repository,
        image_pull_policy=K8sImagePullPolicy(args.pull),
    )

    if not cli_challenge_wrapper(
        root_directory=cli_context.root_directory,
        challenges=args.challenge if args.challenge else None,
        context=context,
        callback=build,
        console=cli_context.console,
    ):
        return False

    return build_root(output=context.output, public_ports=context.public_ports)
