import dataclasses
import enum
import typing

import pydantic

from .path import FilePath, PathContext


class Language(enum.Enum):
    English = "en"
    French = "fr"


@dataclasses.dataclass(frozen=True)
class TextContext:
    root: str


class Text(pydantic.BaseModel):
    language: Language = pydantic.Field(
        Language.English, description="Language of translatable text"
    )
    path: FilePath = pydantic.Field(description="File with text")

    def build(self, context: TextContext) -> typing.Optional[str]:
        if (path := self.path.resolve(PathContext(root=context.root))) is None:
            return None

        with open(path, encoding="utf-8") as h:
            return h.read().strip()

    @classmethod
    def build_many(cls, texts: typing.Sequence["Text"], context: TextContext) -> str:
        return "\n\n---\n\n".join(
            text.build(context) or "FILE NOT FOUND" for text in texts
        )
