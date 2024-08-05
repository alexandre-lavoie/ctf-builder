import typing

from ..schema import ChallengeFlag

from .args import BuildArgs


class BuildFlag:
    @classmethod
    def build(cls, root: str, flag: ChallengeFlag) -> typing.List[str]:
        if (args := BuildArgs.get(flag.values).build(root, flag.values)) is None:
            return []

        return list(args.values())
