import typing

import pydantic

from .text import Text


class Hint(pydantic.BaseModel):
    texts: typing.List[Text] = pydantic.Field(
        description=("List of translatable texts")
    )
    cost: int = pydantic.Field(default=0, description="Cost of hint")
