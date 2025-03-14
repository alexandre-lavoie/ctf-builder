import enum
import typing

import pydantic


class K8sMetadata(pydantic.BaseModel):
    name: typing.Optional[str] = pydantic.Field(default=None)
    labels: typing.Dict[str, str] = pydantic.Field(default_factory=dict)
    annotations: typing.Dict[str, str] = pydantic.Field(default_factory=dict)


class K8sImagePullPolicy(enum.Enum):
    IfNotPresent = "IfNotPresent"
    Always = "Always"
    Never = "Never"


class K8sRestartPolicy(enum.Enum):
    Always = "Always"
    OnFailure = "OnFailure"
    Never = "Never"


class K8sPortProtocol(enum.Enum):
    TCP = "TCP"
    UDP = "UDP"
    SCTP = "SCTP"


class K8sServiceType(enum.Enum):
    ClusterIP = "ClusterIP"
    NodePort = "NodePort"
    LoadBalancer = "LoadBalancer"
    ExternalName = "ExternalName"


class K8sNetworkPolicyType(enum.Enum):
    Ingress = "Ingress"
    Egress = "Egress"


class K8sMatchSelector(pydantic.BaseModel):
    matchLabels: typing.Dict[str, str]


K8sDictSelector = typing.Dict[str, str]


class K8sConfigMap(pydantic.BaseModel):
    apiVersion: typing.Literal["v1"]
    kind: typing.Literal["ConfigMap"]
    metadata: K8sMetadata
    data: typing.Dict[str, str]


class K8sContainerPort(pydantic.BaseModel):
    containerPort: int
    name: typing.Optional[str] = pydantic.Field(default=None)


class K8sContainerResourceLimits(pydantic.BaseModel):
    memory: typing.Optional[str] = pydantic.Field(default=None)
    cpu: typing.Optional[str] = pydantic.Field(default=None)


class K8sContainerResourceRequests(pydantic.BaseModel):
    memory: typing.Optional[str] = pydantic.Field(default=None)
    cpu: typing.Optional[str] = pydantic.Field(default=None)


class K8sContainerResources(pydantic.BaseModel):
    limits: typing.Optional[K8sContainerResourceLimits] = pydantic.Field(default=None)
    requests: typing.Optional[K8sContainerResourceRequests] = pydantic.Field(
        default=None
    )


class K8sContainerEnv(pydantic.BaseModel):
    name: str
    value: typing.Optional[str] = pydantic.Field(default=None)


class K8sContainerLivenessProbeExec(pydantic.BaseModel):
    command: typing.List[str]


class K8sContainerLivenessProbe(pydantic.BaseModel):
    exec: typing.Optional[K8sContainerLivenessProbeExec] = pydantic.Field(default=None)
    initialDelaySeconds: int = pydantic.Field(default=0)
    periodSeconds: int = pydantic.Field(default=10)
    timeoutSeconds: int = pydantic.Field(default=1)
    successThreshold: int = pydantic.Field(default=1)
    failureThreshold: int = pydantic.Field(default=3)


class K8sVolumeMount(pydantic.BaseModel):
    name: str
    mountPath: str
    subPath: typing.Optional[str] = pydantic.Field(default=None)
    readOnly: typing.Optional[bool] = pydantic.Field(default=None)


class K8sContainer(pydantic.BaseModel):
    name: str
    image: str
    imagePullPolicy: K8sImagePullPolicy = pydantic.Field(
        default=K8sImagePullPolicy.Always
    )
    ports: typing.List[K8sContainerPort] = pydantic.Field(default_factory=list)
    resources: typing.Optional[K8sContainerResources] = pydantic.Field(default=None)
    command: typing.Optional[typing.List[str]] = pydantic.Field(default=None)
    args: typing.Optional[typing.List[str]] = pydantic.Field(default=None)
    env: typing.List[K8sContainerEnv] = pydantic.Field(default_factory=list)
    stdin: bool = pydantic.Field(default=False)
    tty: bool = pydantic.Field(default=False)
    restartPolicy: typing.Optional[K8sRestartPolicy] = pydantic.Field(default=None)
    livenessProbe: typing.Optional[K8sContainerLivenessProbe] = pydantic.Field(
        default=None
    )
    volumeMounts: typing.List[K8sVolumeMount] = pydantic.Field(default_factory=list)


class K8sKeyPath(pydantic.BaseModel):
    key: str
    path: str


class K8sVolumeConfigMap(pydantic.BaseModel):
    name: str
    items: typing.List[K8sKeyPath] = pydantic.Field(default_factory=list)


class K8sVolume(pydantic.BaseModel):
    name: str
    configMap: typing.Optional[K8sVolumeConfigMap] = pydantic.Field(default=None)


class K8sPodSpec(pydantic.BaseModel):
    containers: typing.List[K8sContainer] = pydantic.Field(default_factory=list)
    volumes: typing.List[K8sVolume] = pydantic.Field(default_factory=list)


class K8sPodBody(pydantic.BaseModel):
    metadata: K8sMetadata
    spec: K8sPodSpec


class K8sPod(K8sPodBody):
    apiVersion: typing.Literal["v1"]
    kind: typing.Literal["Pod"]


class K8sPodTemplate(K8sPodBody):
    pass


class K8sDeploymentSpec(pydantic.BaseModel):
    replicas: int = pydantic.Field(default=1)
    selector: K8sMatchSelector
    template: K8sPodTemplate


class K8sDeployment(pydantic.BaseModel):
    apiVersion: typing.Literal["apps/v1"]
    kind: typing.Literal["Deployment"]
    metadata: K8sMetadata
    spec: K8sDeploymentSpec


class K8sList(pydantic.BaseModel):
    apiVersion: typing.Literal["v1"]
    kind: typing.Literal["List"]
    metadata: K8sMetadata
    items: typing.List["K8sKind"] = pydantic.Field(default_factory=list)


class K8sServicePort(pydantic.BaseModel):
    name: typing.Optional[str] = pydantic.Field(default=None)
    protocol: K8sPortProtocol = pydantic.Field(default=K8sPortProtocol.TCP)
    port: int
    targetPort: typing.Optional[typing.Union[str, int]] = pydantic.Field(default=None)
    nodePort: typing.Optional[int] = pydantic.Field(default=None)


class K8sServiceSpec(pydantic.BaseModel):
    type: K8sServiceType = pydantic.Field(default=K8sServiceType.ClusterIP)
    selector: K8sDictSelector
    ports: typing.List[K8sServicePort] = pydantic.Field(default_factory=list)


class K8sService(pydantic.BaseModel):
    apiVersion: typing.Literal["v1"]
    kind: typing.Literal["Service"]
    metadata: K8sMetadata
    spec: K8sServiceSpec


class K8sNetworkPolicySelector(pydantic.BaseModel):
    podSelector: typing.Optional[K8sMatchSelector] = pydantic.Field(default=None)


class K8sNetworkPolicyPort(pydantic.BaseModel):
    name: typing.Optional[str] = pydantic.Field(default=None)
    protocol: K8sPortProtocol = pydantic.Field(default=K8sPortProtocol.TCP)
    port: int
    targetPort: typing.Optional[typing.Union[str, int]] = pydantic.Field(default=None)


class K8sNetworkPolicyIngress(pydantic.BaseModel):
    from_: typing.List[K8sNetworkPolicySelector] = pydantic.Field(
        default_factory=list, alias="from"
    )
    ports: typing.Optional[typing.List[K8sNetworkPolicyPort]] = pydantic.Field(
        default=None
    )


class K8sNetworkPolicyEgress(pydantic.BaseModel):
    to: typing.List[K8sNetworkPolicySelector] = pydantic.Field(default_factory=list)
    ports: typing.Optional[typing.List[K8sNetworkPolicyPort]] = pydantic.Field(
        default=None
    )


class K8sNetworkPolicySpec(pydantic.BaseModel):
    name: typing.Optional[str] = pydantic.Field(default=None)
    podSelector: K8sMatchSelector
    policyTypes: typing.List[K8sNetworkPolicyType] = pydantic.Field(
        default_factory=list
    )
    ingress: typing.Optional[typing.List[K8sNetworkPolicyIngress]] = pydantic.Field(
        default=None
    )


class K8sNetworkPolicy(pydantic.BaseModel):
    apiVersion: typing.Literal["networking.k8s.io/v1"]
    kind: typing.Literal["NetworkPolicy"]
    metadata: K8sMetadata
    spec: K8sNetworkPolicySpec


K8sKind = typing.Union[
    K8sConfigMap, K8sDeployment, K8sList, K8sNetworkPolicy, K8sPod, K8sService
]
