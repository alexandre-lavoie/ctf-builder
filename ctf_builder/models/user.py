import pydantic


class User(pydantic.BaseModel):
    name: str
    email: str
