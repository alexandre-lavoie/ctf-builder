import typing

import pydantic


class Memory(pydantic.BaseModel):
    min: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Minimum memory limit expressed as a int or float with a quantity suffix (E, P, T, G, M, k)",
    )
    max: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Maximum memory limit expressed as a int or float with a quantity suffix (E, P, T, G, M, k)",
    )
