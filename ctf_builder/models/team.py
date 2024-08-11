import typing

import pydantic

from .user import User


class Team(pydantic.BaseModel):
    name: str
    email: str
    users: typing.List[User]


class TeamFile(pydantic.BaseModel):
    teams: typing.List[Team]
