import abc
import typing

from ..schema import Args, ArgsList, ArgsMap, ArgsEnv

from .utils import subclass_get


T = typing.TypeVar("T", bound=Args)


class BuildArgs(typing.Generic[T], abc.ABC):
    @classmethod
    def get(cls, obj: Args) -> typing.Type["BuildArgs"]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, args: T) -> typing.Optional[typing.Dict[str, str]]:
        pass


class BuildArgsList(BuildArgs[ArgsList]):
    @classmethod
    def build(cls, root: str, args: ArgsList) -> typing.Optional[typing.Dict[str, str]]:
        return {str(i): v for i, v in enumerate(args.list)}


class BuildArgsMap(BuildArgs[ArgsMap]):
    @classmethod
    def build(cls, root: str, args: ArgsMap) -> typing.Optional[typing.Dict[str, str]]:
        return args.map


class BuildArgsEnv(BuildArgs[ArgsEnv]):
    @classmethod
    def build(cls, root: str, args: ArgsEnv) -> typing.Optional[typing.Dict[str, str]]:
        path = args.path.resolve(root)
        if path is None:
            return None

        with open(path) as h:
            data = h.read()

        key_set = set(args.keys) if args.keys else None
        out = {}
        for line in data.split("\n"):
            if (offset := line.find("=")) == -1:
                continue

            key, value = line[:offset], line[offset + 1 :]
            if key_set and key not in key_set:
                continue

            out[key] = value

        return out
