import typing

from ..schema import ChallengeFlag

from .args import BuildArgs

class BuildFlag:
    @classmethod
    def build(cls, root: str, flag: ChallengeFlag) -> typing.List[str]:
        ba = BuildArgs.get(flag.values)
        if ba is None:
            return []

        m = ba.build(root, flag.values)
        if m is None:
            return []

        return list(m.values())
