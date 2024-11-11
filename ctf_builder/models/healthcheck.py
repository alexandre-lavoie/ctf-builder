import pydantic


class Healthcheck(pydantic.BaseModel):
    """
    Script to check health of resource.
    """

    test: str = pydantic.Field(description="Command to in an OS shell")
    interval: float = pydantic.Field(
        default=1, description="Time between checks in seconds"
    )
    timeout: float = pydantic.Field(
        default=1, description="Time to wait to consider hung in seconds"
    )
    retries: int = pydantic.Field(
        default=3, description="Time to wait to consider hung in seconds"
    )
    start_period: float = pydantic.Field(
        default=0, description="Time to wait to start checking in seconds"
    )
