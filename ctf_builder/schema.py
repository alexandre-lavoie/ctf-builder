import abc
import dataclasses
import enum
import os
import typing

def _meta_comment(comment: str) -> typing.Dict[str, str]:
    return {"comment": comment}

@dataclasses.dataclass(frozen=True)
class Path(abc.ABC):
    value: str = dataclasses.field(metadata=_meta_comment("Raw path to resource"))

    @abc.abstractmethod
    def resolve(self, root: str) -> typing.Optional[str]:
        return None

@dataclasses.dataclass(frozen=True)
class PathFile(Path):
    def resolve(self, root: str) -> typing.Optional[str]:
        path = os.path.join(root, self.value)

        if not os.path.isfile(path):
            return None
        
        return path

@dataclasses.dataclass(frozen=True)
class PathDirectory(Path):
    def resolve(self, root: str) -> typing.Optional[str]:
        path = os.path.join(root, self.value)

        if not os.path.isdir(path):
            return None
        
        return path

@dataclasses.dataclass(frozen=True)
class Translation(abc.ABC):
    path: PathFile = dataclasses.field(metadata=_meta_comment("Path to translated markdown"))

@dataclasses.dataclass(frozen=True)
class TranslationFrench(Translation):
    pass

@dataclasses.dataclass(frozen=True)
class TranslationEnglish(Translation):
    pass

@dataclasses.dataclass(frozen=True)
class Args(abc.ABC):
    pass

@dataclasses.dataclass(frozen=True)
class ArgsMap(Args):
    map: typing.Dict[str, str] = dataclasses.field(metadata=_meta_comment("Dictionary of key/value pairs"))

@dataclasses.dataclass(frozen=True)
class ArgsList(Args):
    list: typing.List[str] = dataclasses.field(metadata=_meta_comment("List of values"))

@dataclasses.dataclass(frozen=True)
class ArgsEnv(Args):
    path: PathFile = dataclasses.field(metadata=_meta_comment("Path to key/value pairs file"))
    keys: typing.List[str] = dataclasses.field(default_factory=list, metadata=_meta_comment("Keys to use in key/value pair file, empty selects all keys"))

@dataclasses.dataclass(frozen=True)
class FileMap:
    source: PathFile = dataclasses.field(metadata=_meta_comment("Path from source system"))
    destination: PathFile = dataclasses.field(metadata=_meta_comment("Path to target system"))

@dataclasses.dataclass(frozen=True)
class PortProtocol(enum.Enum):
    HTTP="http"
    HTTPS="https"
    TCP="tcp"
    UDP="udp"

@dataclasses.dataclass(frozen=True)
class Port:
    port: int = dataclasses.field(metadata=_meta_comment("Port value"))
    protocol: PortProtocol = dataclasses.field(default=PortProtocol.TCP, metadata=_meta_comment("Protocol to use for port"))
    public: bool = dataclasses.field(default=False, metadata=_meta_comment("Is this port exposed to the internet?"))

@dataclasses.dataclass(frozen=True)
class Attachment(abc.ABC):
    pass

@dataclasses.dataclass(frozen=True)
class AttachmentFile(Attachment):
    path: PathFile = dataclasses.field(metadata=_meta_comment("Path to attachment file"))
    name: typing.Optional[str] = dataclasses.field(default=None, metadata=_meta_comment("Name of the attachment, if not file.ext"))

@dataclasses.dataclass(frozen=True)
class AttachmentDirectory(Attachment):
    path: PathDirectory = dataclasses.field(metadata=_meta_comment("Path to attachment directory that will be converted to zip"))
    name: typing.Optional[str] = dataclasses.field(default=None, metadata=_meta_comment("Name of the attachment, if not directory.zip"))

@dataclasses.dataclass(frozen=True)
class Builder(abc.ABC):
    pass

@dataclasses.dataclass(frozen=True)
class BuilderDocker(Builder):
    path: typing.Optional[PathFile] = dataclasses.field(default=None, metadata=_meta_comment("Path to Dockerfile"))
    args: typing.List[Args] = dataclasses.field(default_factory=list, metadata=_meta_comment("Build arguments for Dockerfile"))
    files: typing.List[FileMap] = dataclasses.field(default_factory=list, metadata=_meta_comment("Files to map after build"))

@dataclasses.dataclass(frozen=True)
class Deployer(abc.ABC):
    pass

@dataclasses.dataclass(frozen=True)
class DeployerDocker(Deployer):
    name: str = dataclasses.field(metadata=_meta_comment("Hostname on network"))
    path: typing.Optional[PathFile] = dataclasses.field(default=None, metadata=_meta_comment("Path to Dockerfile"))
    args: typing.List[Args] = dataclasses.field(default_factory=list, metadata=_meta_comment("Build arguments for Dockerfile"))
    env: typing.List[Args] = dataclasses.field(default_factory=list, metadata=_meta_comment("Environments for Dockerfile"))
    ports: typing.List[Port] = dataclasses.field(default_factory=list, metadata=_meta_comment("Ports for deployment"))

@dataclasses.dataclass(frozen=True)
class ChallengeFlag:
    regex: bool = dataclasses.field(metadata=_meta_comment("Is this flag regex?"))
    case_sensitive: bool = dataclasses.field(metadata=_meta_comment("Is this flag case sensitive?"))
    values: Args

@dataclasses.dataclass(frozen=True)
class ChallengeHint:
    texts: typing.List[Translation] = dataclasses.field(metadata=_meta_comment("Translated hint texts"))
    cost: int = dataclasses.field(default=0, metadata=_meta_comment("Cost of hint"))

@dataclasses.dataclass(frozen=True)
class ChallengeHost:
    index: int = dataclasses.field(metadata=_meta_comment("Index of host in deploy array"))
    path: str = dataclasses.field(default="", metadata=_meta_comment("Path to resource"))

@dataclasses.dataclass(frozen=True)
class Challenge:
    category: str = dataclasses.field(metadata=_meta_comment("Category of challenge"))
    name: typing.Optional[str] = dataclasses.field(default=None, metadata=_meta_comment("Subname of challenge, prefixed by track name"))
    descriptions: typing.List[Translation] = dataclasses.field(default_factory=list, metadata=_meta_comment("Translated description texts"))
    value: int = dataclasses.field(default=0, metadata=_meta_comment("Point value of challenge"))
    host: typing.Optional[ChallengeHost] = dataclasses.field(default=None, metadata=_meta_comment("Host of challenge"))
    flags: typing.List[ChallengeFlag] = dataclasses.field(default_factory=list, metadata=_meta_comment("Flags for challenge"))
    hints: typing.List[ChallengeHint] = dataclasses.field(default_factory=list, metadata=_meta_comment("Hints for challenge"))
    attachments: typing.List[Attachment] = dataclasses.field(default_factory=list, metadata=_meta_comment("Attachments file/directory to challenge"))
    prerequisites: typing.List[int] = dataclasses.field(default_factory=list, metadata=_meta_comment("Offset in track of previous prerequisit challenges"))
    next: typing.Optional[int] = dataclasses.field(default=None, metadata=_meta_comment("Next challenge"))

@dataclasses.dataclass(frozen=True)
class Track:
    name: str = dataclasses.field(metadata=_meta_comment("Name of track/challenge"))
    active: typing.Optional[bool] = dataclasses.field(default=False, metadata=_meta_comment("Is this track ready to be used?"))
    challenges: typing.List[Challenge] = dataclasses.field(default_factory=list, metadata=_meta_comment("Challenges for this track, can be a single challenge"))
    build: typing.List[Builder] = dataclasses.field(default_factory=list, metadata=_meta_comment("Build scripts for static file challenges, not required"))
    deploy: typing.List[Deployer] = dataclasses.field(default_factory=list, metadata=_meta_comment("Deployment scripts for network challenges, not required"))
