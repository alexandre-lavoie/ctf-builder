import abc
import dataclasses
import enum
import typing

from .error import ParseError
from .schema import Track, Path

SUBCLASS = typing.TypeVar("SUBCLASS")
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


def __expected(ptype: typing.Type) -> typing.List[str]:
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
    ptype: typing.Any, data: typing.Any, key_path: str = ""
) -> typing.Tuple[typing.Optional[typing.Any], typing.Sequence[ParseError]]:
    origin = typing.get_origin(ptype)
    args = typing.get_args(ptype)

    if origin == typing.Union and len(args) == 2 and args[1] == type(None):
        # typing.Optional[...]
        return __parse_type(args[0], data, key_path)

    errors: typing.List[ParseError] = []
    if origin == dict:
        # typing.Dict[str, ...]

        assert args[0] == str, "Only str keys are supported"

        if not isinstance(data, dict):
            return None, [ParseError(key_path, __expected(ptype))]

        dict_output: typing.Dict[str, typing.Any] = {}
        for k, v in data.items():
            if not isinstance(k, str):
                continue

            d, err = __parse_type(args[1], v, f"{key_path}.{k}")

            if err:
                errors += err
            else:
                dict_output[k] = d

        return dict_output, errors
    elif origin == list:
        # typing.List[...]

        if not isinstance(data, list):
            return None, [ParseError(key_path, __expected(ptype))]

        list_output = []
        for i, v in enumerate(data):
            d, err = __parse_type(args[0], v, f"{key_path}.{i}")

            if err:
                errors += err
            else:
                list_output.append(d)

        return list_output, errors
    elif ptype == float:
        if isinstance(data, float):
            return data, []
        elif isinstance(data, int):
            return float(data), []
        else:
            return None, [ParseError(key_path, __expected(ptype))]
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
    elif dataclasses.is_dataclass(ptype):
        if not isinstance(data, dict):
            return None, [ParseError(key_path, __expected(ptype))]

        if ptype.__base__ == abc.ABC:
            tname = data.get("$type")
            if not isinstance(tname, str):
                return None, [ParseError(f"{key_path}.$type", __expected(str))]

            parent = ptype

            next_ptype = __get_subclass_from_name(ptype, tname)
            if next_ptype is None:
                return None, [
                    ParseError(f"{key_path}.$type", __get_subclass_names(parent))
                ]
            ptype = next_ptype

        type_fields = {}
        for data_field in dataclasses.fields(ptype):
            value = data.get(data_field.name)
            if value is None:
                if not isinstance(data_field.default, dataclasses._MISSING_TYPE):
                    d, err = data_field.default, []
                elif not isinstance(
                    data_field.default_factory, dataclasses._MISSING_TYPE
                ):
                    d, err = data_field.default_factory(), []
                else:
                    d, err = None, [
                        ParseError(
                            f"{key_path}.{data_field.name}", __expected(data_field.type)
                        )
                    ]
            else:
                d, err = __parse_type(
                    data_field.type, value, f"{key_path}.{data_field.name}"
                )

            if err:
                errors += err
            else:
                type_fields[data_field.name] = d

        if errors:
            return None, errors

        return ptype(**type_fields), []
    else:
        assert False, f"unsupported {ptype}"


def parse_track(
    data: typing.Dict,
) -> typing.Tuple[typing.Optional[Track], typing.Sequence[ParseError]]:
    if data is None:
        return None, [ParseError("", __expected(Track))]

    return __parse_type(Track, data)
