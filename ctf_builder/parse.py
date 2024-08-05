import enum

from .error import ParseError
from .schema import *

SUBCLASS = typing.TypeVar("SUBCLASS")
PTYPE = typing.TypeVar("PTYPE")
ATOM_TYPES = (str, int, float, bool)


def __get_subclass_from_name(
    target: typing.Type[SUBCLASS], name: str
) -> typing.Optional[typing.Type[SUBCLASS]]:
    self_name = target.__name__

    for subclass in target.__subclasses__():
        if subclass.__name__[len(self_name) :].lower() == name:
            return subclass

    return None


def __get_subclass_names(target: typing.Type) -> typing.List[str]:
    self_name = target.__name__

    names = []
    for subclass in target.__subclasses__():
        names.append(subclass.__name__[len(self_name) :].lower())

    return names


def __expected(ptype: typing.Type) -> str:
    if ptype in ATOM_TYPES:
        return [ptype.__name__]
    elif typing.get_origin(ptype) == list:
        return [list.__name__]
    elif ptype.__base__ == Path:
        return ["path"]
    elif ptype.__base__ == enum.Enum:
        return [e.value for e in ptype]
    else:
        return ["dict"]


def __parse_type(
    ptype: typing.Type[PTYPE], data: typing.Any, key_path: str = ""
) -> typing.Tuple[typing.Optional[PTYPE], typing.Sequence[ParseError]]:
    origin = typing.get_origin(ptype)
    args = typing.get_args(ptype)

    if origin == typing.Union and len(args) == 2 and args[1] == type(None):
        # typing.Optional[...]
        return __parse_type(args[0], data, key_path)

    if origin == dict:
        # typing.Dict[str, ...]

        assert args[0] == str, "Only str keys are supported"

        if not isinstance(data, dict):
            return None, [ParseError(key_path, __expected(ptype))]

        output = {}
        errors = []
        for k, v in data.items():
            d, err = __parse_type(args[1], v, f"{key_path}.{k}")

            if err:
                errors += err
            else:
                output[k] = d

        return output, errors
    elif origin == list:
        # typing.List[...]

        if not isinstance(data, list):
            return None, [ParseError(key_path, __expected(ptype))]

        output = []
        errors = []
        for i, v in enumerate(data):
            d, err = __parse_type(args[0], v, f"{key_path}.{i}")

            if err:
                errors += err
            else:
                output.append(d)

        return output, errors
    elif ptype in ATOM_TYPES:
        if not isinstance(data, ptype):
            return None, [ParseError(key_path, __expected(ptype))]

        return data, []
    elif ptype.__base__ == Path:
        if not isinstance(data, str):
            return None, [ParseError(key_path, __expected(ptype))]

        return ptype(data), []
    elif ptype.__base__ == enum.Enum:
        try:
            return ptype(data), []
        except ValueError:
            return None, [ParseError(key_path, __expected(ptype))]
    else:
        if not isinstance(data, dict):
            return None, [ParseError(key_path, __expected(ptype))]

        if ptype.__base__ == abc.ABC:
            tname = data.get("$type")

            parent = ptype
            ptype = __get_subclass_from_name(ptype, tname)
            if ptype is None:
                return None, [
                    ParseError(f"{key_path}.$type", __get_subclass_names(parent))
                ]

        fields = {}
        errors = []
        for field in dataclasses.fields(ptype):
            value = data.get(field.name)
            if value is None:
                if not isinstance(field.default, dataclasses._MISSING_TYPE):
                    d, err = field.default, []
                elif not isinstance(field.default_factory, dataclasses._MISSING_TYPE):
                    d, err = field.default_factory(), []
                else:
                    d, err = None, [
                        ParseError(f"{key_path}.{field.name}", __expected(field.type))
                    ]
            else:
                d, err = __parse_type(field.type, value, f"{key_path}.{field.name}")

            if err:
                errors += err
            else:
                fields[field.name] = d

        if errors:
            return None, errors

        return ptype(**fields), []


def parse_track(
    data: typing.Dict,
) -> typing.Tuple[typing.Optional[Track], typing.Sequence[ParseError]]:
    if data is None:
        return None, [ParseError("", __expected(Track))]

    return __parse_type(Track, data)
