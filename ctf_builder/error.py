import abc
import dataclasses
import os.path
import typing
import sys

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
class ParseError(LibError):
    path: str
    expected: typing.List[str]

@dataclasses.dataclass
class SkipError(LibError):
    pass

def print_errors(path: str, errors: typing.Sequence[typing.Union[LibError]]) -> None:
    if path:
        name = os.path.basename(os.path.dirname(path))
        prefix = f"{name}: "
    else:
        prefix = ""

    if not errors:
        print(f"{prefix}OK")
    elif all(isinstance(error, SkipError) for error in errors):
        print(f"{prefix}SKIP")
    else:
        print(f"{prefix}ERROR", file=sys.stderr)

        for error in errors:
            if isinstance(error, ParseError):
                print(f"- Parse: path {error.path} > expected [{", ".join(error.expected)}]")
            elif isinstance(error, BuildError):
                print(f"- Build: {error.msg}")
            elif isinstance(error, DeployError):
                print(f"- Deploy: {error.msg}")
            else:
                print(f"- {type(error)}: {error}")
