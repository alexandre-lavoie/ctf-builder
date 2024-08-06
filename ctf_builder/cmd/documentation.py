import abc
import argparse
import dataclasses
import enum
import json
import os
import os.path
import typing

from ..config import CLASS_TYPE_COMMENT, CLASS_TYPE_FIELD, COMMENT_FIELD_NAME
from ..schema import Path, Track
from .common import CliContext


ATOM_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclasses.dataclass(frozen=True)
class Args:
    output: str


def is_optional(ptype: typing.Type[typing.Any]) -> bool:
    origin = typing.get_origin(ptype)
    args = typing.get_args(ptype)

    return origin == typing.Union and len(args) == 2 and args[1] == type(None)


def document_type(
    ptype: typing.Type[typing.Any], description: typing.Optional[str] = None
) -> typing.Dict[str, typing.Any]:
    origin = typing.get_origin(ptype)
    args = typing.get_args(ptype)

    out: typing.Dict[str, typing.Any]
    if is_optional(ptype):
        return document_type(args[0], description)
    elif origin == dict:
        out = {
            "type": "object",
            "patternProperties": {"^[a-zA-Z0-9_]+$": document_type(args[1])},
        }
    elif origin == list:
        out = {"type": "array", "items": document_type(args[0])}
    elif ptype in ATOM_TYPES:
        out = {"type": ATOM_TYPES[ptype]}
    elif ptype.__base__ == abc.ABC:
        subclasses = ptype.__subclasses__()
        values = [document_type(subclass) for subclass in subclasses]

        for subclass, obj in zip(subclasses, values):
            name = subclass.__name__[len(ptype.__name__) :].lower()

            obj["required"] = [CLASS_TYPE_FIELD, *obj["required"]]
            obj["properties"] = {
                CLASS_TYPE_FIELD: {
                    "description": CLASS_TYPE_COMMENT,
                    "type": "string",
                    "enum": [name],
                },
                **obj["properties"],
            }

        out = {"type": "object", "oneOf": values}
    elif ptype.__base__ == Path:
        out = {
            "type": "string",
        }
    elif ptype.__base__ == enum.Enum:
        out = {"type": "string", "enum": [e.value for e in ptype]}
    else:
        properties = {}
        required = []
        for field in dataclasses.fields(ptype):
            if (
                not is_optional(field.type)
                and isinstance(field.default, dataclasses._MISSING_TYPE)
                and isinstance(field.default_factory, dataclasses._MISSING_TYPE)
            ):
                required.append(field.name)

            properties[field.name] = document_type(
                field.type, field.metadata.get(COMMENT_FIELD_NAME)
            )

        out = {"type": "object", "required": required, "properties": properties}

    if description is not None:
        out = {"description": description, **out}

    return out


def cli_args(parser: argparse.ArgumentParser, root_directory: str) -> None:
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory",
        default=os.path.join(root_directory, "doc"),
    )


def cli(args: Args, cli_context: CliContext) -> bool:
    if not os.path.isdir(os.path.dirname(args.output)):
        return False

    os.makedirs(args.output, exist_ok=True)

    challenge_json = os.path.join(args.output, "challenge.json")

    with open(challenge_json, "w") as h:
        json.dump(document_type(Track), h, indent=2)

    return True
