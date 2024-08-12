import dataclasses
import enum
import typing

import pydantic


T = typing.TypeVar("T")


class CTFdChallengeState(enum.Enum):
    Visible = "visible"
    Hidden = "hidden"


class CTFdChallengeType(enum.Enum):
    Standard = "standard"
    Hidden = "hidden"


class CTFdChallengeRequirements(pydantic.BaseModel):
    anonymize: typing.Optional[bool] = pydantic.Field(default=None)
    prerequisites: typing.Optional[typing.List[int]] = pydantic.Field(default=None)


class CTFdChallenge(pydantic.BaseModel):
    id: int
    name: typing.Optional[str] = pydantic.Field(default=None)
    description: typing.Optional[str] = pydantic.Field(default=None)
    connection_info: typing.Optional[str] = pydantic.Field(default=None)
    next_id: typing.Optional[int] = pydantic.Field(default=None)
    max_attempts: typing.Optional[int] = pydantic.Field(default=None)
    value: typing.Optional[int] = pydantic.Field(default=None)
    category: typing.Optional[str] = pydantic.Field(default=None)
    type: typing.Optional[CTFdChallengeType] = pydantic.Field(
        default=CTFdChallengeType.Standard
    )
    state: typing.Optional[CTFdChallengeState] = pydantic.Field(default=None)
    requirements: typing.Optional[CTFdChallengeRequirements] = pydantic.Field(
        default=None
    )
    solves: typing.Optional[int] = pydantic.Field(default=None)
    solved_by_me: typing.Optional[bool] = pydantic.Field(default=None)


class CTFdFile(pydantic.BaseModel):
    id: int
    type: typing.Optional[str] = pydantic.Field(default=None)
    location: typing.Optional[str] = pydantic.Field(default=None)
    sha1sum: typing.Optional[str] = pydantic.Field(default=None)


class CTFdFlagType(enum.Enum):
    Static = "static"
    Regex = "regex"


class CTFdFlagData(enum.Enum):
    CaseSensitive = ""
    CaseInsensitive = "case_insensitive"


class CTFdFlag(pydantic.BaseModel):
    id: int
    challenge_id: typing.Optional[int] = pydantic.Field(default=None)
    type: typing.Optional[CTFdFlagType] = pydantic.Field(default=None)
    content: typing.Optional[str] = pydantic.Field(default=None)
    data: typing.Optional[CTFdFlagData] = pydantic.Field(default=None)


class CTFdHintRequirements(pydantic.BaseModel):
    prerequisites: typing.Optional[typing.List[int]] = pydantic.Field(default=None)


class CTFdHint(pydantic.BaseModel):
    id: int
    type: typing.Optional[str] = pydantic.Field(default=None)
    challenge_id: typing.Optional[int] = pydantic.Field(default=None)
    content: typing.Optional[str] = pydantic.Field(default=None)
    cost: typing.Optional[int] = pydantic.Field(default=None)
    requirements: typing.Optional[CTFdHintRequirements] = pydantic.Field(default=None)


class CTFdSetupUserMode(enum.Enum):
    Users = "users"
    Teams = "teams"


class CTFdSetupVisibility(enum.Enum):
    Public = "public"
    Private = "private"
    Admins = "admins"


class CTFdSetup(pydantic.BaseModel):
    ctf_name: str = pydantic.Field(default="")
    ctf_description: str = pydantic.Field(default="")
    user_mode: CTFdSetupUserMode = pydantic.Field(default=CTFdSetupUserMode.Users)
    challenge_visibility: CTFdSetupVisibility = pydantic.Field(
        default=CTFdSetupVisibility.Admins
    )
    score_visibility: CTFdSetupVisibility = pydantic.Field(
        default=CTFdSetupVisibility.Admins
    )
    account_visibility: CTFdSetupVisibility = pydantic.Field(
        default=CTFdSetupVisibility.Admins
    )
    registration_visibility: CTFdSetupVisibility = pydantic.Field(
        default=CTFdSetupVisibility.Admins
    )
    verify_emails: bool = pydantic.Field(default=False)
    name: str = pydantic.Field(default="")
    email: str = pydantic.Field(default="")
    password: str = pydantic.Field(default="")
    ctf_theme: str = pydantic.Field(default="core-beta")
    theme_color: str = pydantic.Field(default="")
    start: str = pydantic.Field(default="")
    end: str = pydantic.Field(default="")
    nonce: str = pydantic.Field(default="")
    team_size: int = pydantic.Field(default=0)
    ctf_logo: str = pydantic.Field(default="")
    ctf_banner: str = pydantic.Field(default="")
    ctf_small_icon: str = pydantic.Field(default="")


class CTFdTeam(pydantic.BaseModel):
    id: int
    oauth_id: typing.Optional[int] = pydantic.Field(default=None)
    name: typing.Optional[str] = pydantic.Field(default=None)
    email: typing.Optional[str] = pydantic.Field(default=None)
    password: typing.Optional[str] = pydantic.Field(default=None)
    secret: typing.Optional[str] = pydantic.Field(default=None)
    website: typing.Optional[str] = pydantic.Field(default=None)
    affiliation: typing.Optional[str] = pydantic.Field(default=None)
    country: typing.Optional[str] = pydantic.Field(default=None)
    bracket_id: typing.Optional[int] = pydantic.Field(default=None)
    hidden: typing.Optional[bool] = pydantic.Field(default=None)
    banned: typing.Optional[bool] = pydantic.Field(default=None)
    captain_id: typing.Optional[int] = pydantic.Field(default=None)
    created: typing.Optional[str] = pydantic.Field(default=None)


class CTFdFileUploadType(enum.Enum):
    Challenge = "challenge"


@dataclasses.dataclass
class CTFdFileUpload:
    challenge: int
    type: CTFdFileUploadType
    file_name: str
    file_data: typing.BinaryIO


class CTFdUserType(enum.Enum):
    User = "user"
    Admin = "admin"


class CTFdUser(pydantic.BaseModel):
    id: int
    oauth_id: typing.Optional[int] = pydantic.Field(default=None)
    name: typing.Optional[str] = pydantic.Field(default=None)
    email: typing.Optional[str] = pydantic.Field(default=None)
    password: typing.Optional[str] = pydantic.Field(default=None)
    type: typing.Optional[CTFdUserType] = pydantic.Field(default=CTFdUserType.User)
    secret: typing.Optional[str] = pydantic.Field(default=None)
    affiliation: typing.Optional[str] = pydantic.Field(default=None)
    country: typing.Optional[str] = pydantic.Field(default=None)
    bracket_id: typing.Optional[int] = pydantic.Field(default=None)
    hidden: typing.Optional[bool] = pydantic.Field(default=None)
    banned: typing.Optional[bool] = pydantic.Field(default=None)
    verified: typing.Optional[bool] = pydantic.Field(default=None)
    language: typing.Optional[str] = pydantic.Field(default=None)
    team_id: typing.Optional[int] = pydantic.Field(default=None)
    created: typing.Optional[str] = pydantic.Field(default=None)


class CTFdAccessToken(pydantic.BaseModel):
    id: int
    type: typing.Optional[str] = pydantic.Field(default=None)
    user_id: typing.Optional[int] = pydantic.Field(default=None)
    created: typing.Optional[str] = pydantic.Field(default=None)
    expiration: typing.Optional[str] = pydantic.Field(default=None)
    description: typing.Optional[str] = pydantic.Field(default=None)
    value: typing.Optional[str] = pydantic.Field(default=None)


class CTFdResponse(pydantic.BaseModel, typing.Generic[T]):
    success: bool
    data: typing.Optional[T] = pydantic.Field(default=None)
    message: typing.Optional[str] = pydantic.Field(default=None)
    errors: typing.List[str] = pydantic.Field(default_factory=list)
