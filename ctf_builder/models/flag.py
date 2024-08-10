import dataclasses
import typing

import pydantic

from .arguments import ArgumentContext, Arguments


@dataclasses.dataclass(frozen=True)
class FlagContext:
    root: str


class Flag(pydantic.BaseModel):
    regex: bool = pydantic.Field(description="Is this flag regex?")
    case_sensitive: bool = pydantic.Field(description="Is this flag case sensitive?")
    values: Arguments

    def build(self, context: FlagContext) -> typing.Sequence[str]:
        if (args := self.values.build(ArgumentContext(root=context.root))) is None:
            return []

        return list(args.values())
