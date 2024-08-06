import abc
import dataclasses
import enum
import os
import typing


def _meta_comment(comment: str) -> typing.Dict[str, str]:
    """
    Applies a comment to dataclasses.field to be used in documentation.
    """

    return {"comment": comment}


@dataclasses.dataclass(frozen=True)
class Path(abc.ABC):
    """
    OS path to a resource.
    """

    value: str = dataclasses.field(metadata=_meta_comment("Raw path to resource"))

    @abc.abstractmethod
    def resolve(self, root: str) -> typing.Optional[str]:
        """
        Resolves the path based on a root path.
        """

        return None


@dataclasses.dataclass(frozen=True)
class PathFile(Path):
    """
    Path to an OS file.
    """

    def resolve(self, root: str) -> typing.Optional[str]:
        path = os.path.join(root, self.value)

        if not os.path.isfile(path):
            return None

        return path


@dataclasses.dataclass(frozen=True)
class PathDirectory(Path):
    """
    Path to an OS directory.
    """

    def resolve(self, root: str) -> typing.Optional[str]:
        path = os.path.join(root, self.value)

        if not os.path.isdir(path):
            return None

        return path


@dataclasses.dataclass(frozen=True)
class Translation(abc.ABC):
    """
    Translatable text.
    """

    path: PathFile = dataclasses.field(
        metadata=_meta_comment("Path to translated markdown")
    )


@dataclasses.dataclass(frozen=True)
class TranslationFrench(Translation):
    """
    Translation in French
    """

    pass


@dataclasses.dataclass(frozen=True)
class TranslationEnglish(Translation):
    """
    Translation in English
    """

    pass


@dataclasses.dataclass(frozen=True)
class Args(abc.ABC):
    """
    Map/list like arguments.
    """

    pass


@dataclasses.dataclass(frozen=True)
class ArgsMap(Args):
    """
    Arguments defined as a map.
    """

    map: typing.Dict[str, str] = dataclasses.field(
        metadata=_meta_comment("Dictionary of key/value pairs")
    )


@dataclasses.dataclass(frozen=True)
class ArgsList(Args):
    """
    Arguments defined as a list.
    """

    list: typing.List[str] = dataclasses.field(metadata=_meta_comment("List of values"))


@dataclasses.dataclass(frozen=True)
class ArgsEnv(Args):
    """
    Arguments defined in a key/value part (env) file.
    """

    path: PathFile = dataclasses.field(
        metadata=_meta_comment("Path to key/value pairs file")
    )
    keys: typing.List[str] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment(
            "Keys to use in key/value pair file, empty selects all keys"
        ),
    )


@dataclasses.dataclass(frozen=True)
class FileMap:
    """
    Mapping to move a source file to a destination.
    """

    source: PathFile = dataclasses.field(
        metadata=_meta_comment("Path from source system")
    )
    destination: PathFile = dataclasses.field(
        metadata=_meta_comment("Path to target system")
    )


@dataclasses.dataclass(frozen=True)
class PortProtocol(enum.Enum):
    """
    Type of protocol the port uses.
    """

    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"
    UDP = "udp"


@dataclasses.dataclass(frozen=True)
class Port:
    """
    OS port.
    """

    port: int = dataclasses.field(metadata=_meta_comment("Port value"))
    protocol: PortProtocol = dataclasses.field(
        default=PortProtocol.TCP, metadata=_meta_comment("Protocol to use for port")
    )


@dataclasses.dataclass(frozen=True)
class Attachment(abc.ABC):
    """
    Resource that can be uploaded.
    """

    pass


@dataclasses.dataclass(frozen=True)
class AttachmentFile(Attachment):
    """
    File resource.
    """

    path: PathFile = dataclasses.field(
        metadata=_meta_comment("Path to attachment file")
    )
    name: typing.Optional[str] = dataclasses.field(
        default=None, metadata=_meta_comment("Name of the attachment, if not file.ext")
    )


@dataclasses.dataclass(frozen=True)
class AttachmentDirectory(Attachment):
    """
    Directory resource. Intended to be used to select files recursively.
    """

    path: PathDirectory = dataclasses.field(
        metadata=_meta_comment(
            "Path to attachment directory that will be converted to zip"
        )
    )
    name: typing.Optional[str] = dataclasses.field(
        default=None,
        metadata=_meta_comment("Name of the attachment, if not directory.zip"),
    )


@dataclasses.dataclass(frozen=True)
class Healthcheck:
    """
    Script to check health of resource.
    """

    test: str = dataclasses.field(metadata=_meta_comment("Command to in an OS shell"))
    interval: float = dataclasses.field(
        default=1, metadata=_meta_comment("Time between checks in seconds")
    )
    timeout: float = dataclasses.field(
        default=1, metadata=_meta_comment("Time to wait to consider hung in seconds")
    )
    retries: int = dataclasses.field(
        default=3,
        metadata=_meta_comment("Number of consecutive failures to consider unhealthy"),
    )
    start_period: float = dataclasses.field(
        default=0, metadata=_meta_comment("Time to wait to start checking in seconds")
    )


@dataclasses.dataclass(frozen=True)
class Builder(abc.ABC):
    """
    Automation to build challenges.
    """

    pass


@dataclasses.dataclass(frozen=True)
class BuilderDocker(Builder):
    """
    Builder using Dockerfiles.
    """

    path: typing.Optional[PathFile] = dataclasses.field(
        default=None, metadata=_meta_comment("Path to Dockerfile")
    )
    args: typing.List[Args] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Build arguments for Dockerfile")
    )
    files: typing.List[FileMap] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Files to map after build")
    )


@dataclasses.dataclass(frozen=True)
class Deployer(abc.ABC):
    """
    Automation to deploy challenges.
    """

    pass


@dataclasses.dataclass(frozen=True)
class DeployerDocker(Deployer):
    """
    Deployment using Docker.
    """

    name: typing.Optional[str] = dataclasses.field(
        default=None, metadata=_meta_comment("Hostname on network")
    )
    path: typing.Optional[PathFile] = dataclasses.field(
        default=None, metadata=_meta_comment("Path to Dockerfile")
    )
    args: typing.List[Args] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Build arguments for Dockerfile")
    )
    env: typing.List[Args] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Environments for Dockerfile")
    )
    ports: typing.List[Port] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Ports for deployment")
    )
    healthcheck: typing.Optional[Healthcheck] = dataclasses.field(
        default=None, metadata=_meta_comment("Healtcheck for Dockerfile")
    )


@dataclasses.dataclass(frozen=True)
class Tester(abc.ABC):
    """
    Automation to test challenges
    """

    pass


@dataclasses.dataclass(frozen=True)
class TesterDocker(Tester):
    """
    Testing using Dockerfile.
    """

    challenges: typing.List[int] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment("Challenges to run test on, all by default"),
    )
    path: typing.Optional[PathFile] = dataclasses.field(
        default=None, metadata=_meta_comment("Path to Dockerfile")
    )
    args: typing.List[Args] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Build arguments for Dockerfile")
    )
    env: typing.List[Args] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Environments for Dockerfile")
    )


@dataclasses.dataclass(frozen=True)
class ChallengeFlag:
    """
    CTFd flag.
    """

    regex: bool = dataclasses.field(metadata=_meta_comment("Is this flag regex?"))
    case_sensitive: bool = dataclasses.field(
        metadata=_meta_comment("Is this flag case sensitive?")
    )
    values: Args


@dataclasses.dataclass(frozen=True)
class ChallengeHint:
    """
    CTFd hint.
    """

    texts: typing.List[Translation] = dataclasses.field(
        metadata=_meta_comment("Translated hint texts")
    )
    cost: int = dataclasses.field(default=0, metadata=_meta_comment("Cost of hint"))


@dataclasses.dataclass(frozen=True)
class ChallengeHost:
    """
    Connection for challenge to associated Deployer.
    """

    index: int = dataclasses.field(
        metadata=_meta_comment("Index of host in deploy array")
    )
    path: str = dataclasses.field(
        default="", metadata=_meta_comment("Path to resource")
    )


@dataclasses.dataclass(frozen=True)
class Challenge:
    """
    CTF challenge.
    """

    category: str = dataclasses.field(metadata=_meta_comment("Category of challenge"))
    name: typing.Optional[str] = dataclasses.field(
        default=None,
        metadata=_meta_comment("Subname of challenge, prefixed by track name"),
    )
    descriptions: typing.List[Translation] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Translated description texts")
    )
    value: int = dataclasses.field(
        default=0, metadata=_meta_comment("Point value of challenge")
    )
    host: typing.Optional[ChallengeHost] = dataclasses.field(
        default=None, metadata=_meta_comment("Host of challenge")
    )
    flags: typing.List[ChallengeFlag] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Flags for challenge")
    )
    hints: typing.List[ChallengeHint] = dataclasses.field(
        default_factory=list, metadata=_meta_comment("Hints for challenge")
    )
    attachments: typing.List[Attachment] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment("Attachments file/directory to challenge"),
    )
    prerequisites: typing.List[int] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment("Offset in track of previous prerequisit challenges"),
    )
    next: typing.Optional[int] = dataclasses.field(
        default=None, metadata=_meta_comment("Next challenge")
    )


@dataclasses.dataclass(frozen=True)
class Track:
    """
    Root level collection of challenges and automations.
    """

    name: str = dataclasses.field(metadata=_meta_comment("Name of track/challenge"))
    tag: typing.Optional[str] = dataclasses.field(
        default=None,
        metadata=_meta_comment(
            "Simple name to use for labelling, used cleaned up name by default"
        ),
    )
    active: typing.Optional[bool] = dataclasses.field(
        default=False, metadata=_meta_comment("Is this track ready to be used?")
    )
    challenges: typing.List[Challenge] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment("Challenges for this track, can be a single challenge"),
    )
    build: typing.List[Builder] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment(
            "Build scripts for static file challenges, not required"
        ),
    )
    deploy: typing.List[Deployer] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment(
            "Deployment scripts for network challenges, not required"
        ),
    )
    test: typing.List[Tester] = dataclasses.field(
        default_factory=list,
        metadata=_meta_comment("Test scripts for challenges, not required"),
    )
