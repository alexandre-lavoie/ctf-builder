import typing

import pydantic
import pydantic_core

from ..error import LibError, ParseError
from .attachment import Attachment
from .build import Build
from .deploy import Deploy
from .flag import Flag
from .hint import Hint
from .test import Test
from .text import Text


class Host(pydantic.BaseModel):
    """
    Connection for challenge to associated Deployer.
    """

    index: int = pydantic.Field(description="Index of host in deploy array")
    path: str = pydantic.Field(default="", description="Path to resource")


class Challenge(pydantic.BaseModel):
    """
    CTF challenge.
    """

    category: str = pydantic.Field(description="Category of challenge")
    name: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Subname of challenge, prefixed by track name",
    )
    descriptions: typing.List[Text] = pydantic.Field(
        default_factory=list, description="Translated description texts"
    )
    value: int = pydantic.Field(default=0, description="Point value of challenge")
    host: typing.Optional[Host] = pydantic.Field(
        default=None, description="Host of challenge"
    )
    flags: typing.List[Flag] = pydantic.Field(
        default_factory=list, description="Flags for challenge"
    )
    hints: typing.List[Hint] = pydantic.Field(
        default_factory=list, description="Hints for challenge"
    )
    attachments: typing.List[Attachment] = pydantic.Field(
        default_factory=list,
        description="Attachments file/directory to challenge",
    )
    prerequisites: typing.List[int] = pydantic.Field(
        default_factory=list,
        description="Offset in track of previous prerequisit challenges",
    )
    next: typing.Optional[int] = pydantic.Field(
        default=None, description="Next challenge"
    )


class Track(pydantic.BaseModel):
    """
    Root level collection of challenges and automations.
    """

    name: str = pydantic.Field(description="Name of track/challenge")
    tag: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Simple name to use for labelling, used cleaned up name by default",
    )
    active: typing.Optional[bool] = pydantic.Field(
        default=False, description="Is this track ready to be used?"
    )
    challenges: typing.List[Challenge] = pydantic.Field(
        default_factory=list,
        description="Challenges for this track, can be a single challenge",
    )
    build: typing.List[Build] = pydantic.Field(
        default_factory=list,
        description="Build scripts for static file challenges, not required",
    )
    deploy: typing.List[Deploy] = pydantic.Field(
        default_factory=list,
        description="Deployment scripts for network challenges, not required",
    )
    test: typing.List[Test] = pydantic.Field(
        default_factory=list,
        description="Test scripts for challenges, not required",
    )

    @classmethod
    def parse(
        cls, data: typing.Dict[str, typing.Any]
    ) -> typing.Tuple[typing.Optional["Track"], typing.Sequence[LibError]]:
        try:
            return cls(**data), []
        except pydantic_core._pydantic_core.ValidationError as e:
            return None, [
                ParseError(
                    path=".".join(str(p) for p in error["loc"]),
                    msg=(error.get("msg") or "").lower(),
                )
                for error in e.errors()
            ]
