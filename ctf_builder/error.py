import abc
import dataclasses
import typing

from .logging import LOG


@dataclasses.dataclass
class LibError(abc.ABC):
    pass


@dataclasses.dataclass
class BuildError(LibError):
    msg: str


@dataclasses.dataclass
class DeployError(LibError):
    msg: str


@dataclasses.dataclass
class TestError(LibError):
    msg: str


@dataclasses.dataclass
class ParseError(LibError):
    path: str
    expected: typing.List[str]


@dataclasses.dataclass
class SkipError(LibError):
    pass


def print_errors(prefix: str, errors: typing.Sequence[typing.Union[LibError]]) -> None:
    if not prefix:
        prefix = ""
    else:
        prefix += ": "

    if not errors:
        LOG.warn(f"{prefix}OK")
    elif all(isinstance(error, SkipError) for error in errors):
        LOG.warn(f"{prefix}SKIP")
    else:
        LOG.error(f"{prefix}ERROR")

        for error in errors:
            if isinstance(error, ParseError):
                LOG.error(
                    f"- Parse: path {error.path} > expected [{", ".join(error.expected)}]"
                )
            elif isinstance(error, BuildError):
                LOG.error(f"- Build: {error.msg}")
            elif isinstance(error, DeployError):
                LOG.error(f"- Deploy: {error.msg}")
            elif isinstance(error, TestError):
                LOG.error(f"- Test: {error.msg}")
            else:
                LOG.error(f"- {type(error)}: {error}")


def get_exit_status(errors: typing.Sequence[typing.Union[LibError]]) -> bool:
    if not errors:
        return True

    if all(isinstance(error, SkipError) for error in errors):
        return True

    return False
