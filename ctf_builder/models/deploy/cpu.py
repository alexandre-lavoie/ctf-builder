import typing

import pydantic


class CPU(pydantic.BaseModel):
    min: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Minimum CPU limit expressed as a int or float with/without a quantity suffix (m)",
    )
    max: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Maximum CPU limit expressed as a int or float with/without a quantity suffix (m)",
    )
