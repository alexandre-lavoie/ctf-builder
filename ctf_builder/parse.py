import abc
import dataclasses
import enum
import typing

from .config import CLASS_TYPE_COMMENT, CLASS_TYPE_FIELD, COMMENT_FIELD_NAME
from .error import ParseError
from .schema import Path, Track


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


def __get_subclass_names(target: typing.Type[typing.Any]) -> typing.List[str]:
    self_name = target.__name__

    names = []
    for subclass in target.__subclasses__():
        names.append(subclass.__name__[len(self_name) :].lower())

    return names


def __expected(ptype: typing.Type[typing.Any]) -> typing.List[str]:
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
    ptype: typing.Any,
    data: typing.Any,
    key_path: str = "",
    comment: typing.Optional[str] = None,
) -> typing.Tuple[typing.Optional[typing.Any], typing.Sequence[ParseError]]:
    origin = typing.get_origin(ptype)
    args = typing.get_args(ptype)

    if origin == typing.Union and len(args) == 2 and args[1] == type(None):
        # typing.Optional[...]
        return __parse_type(
            ptype=args[0], data=data, key_path=key_path, comment=comment
        )

    errors: typing.List[ParseError] = []
    if origin == dict:
        # typing.Dict[str, ...]

        assert args[0] == str, "Only str keys are supported"

        if isinstance(data, dict):
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

        if isinstance(data, list):
            list_output = []
            for i, v in enumerate(data):
                d, err = __parse_type(args[0], v, f"{key_path}.{i}")

                if err:
                    errors += err
                else:
                    list_output.append(d)

            return list_output, errors

    elif ptype == float:
        # float

        if isinstance(data, float):
            return data, []
        elif isinstance(data, int):
            return float(data), []

    elif ptype in ATOM_TYPES:
        # str, int, bool

        if isinstance(data, ptype):
            return data, []

    elif ptype.__base__ == Path:
        # Path subclass

        if isinstance(data, str):
            return ptype(data), []

    elif ptype.__base__ == enum.Enum:
        # enum.Enum subclass

        try:
            return ptype(data), []
        except ValueError:
            pass

    elif dataclasses.is_dataclass(ptype):
        # dataclasses.dataclass

        if isinstance(data, dict):
            if ptype.__base__ == abc.ABC:
                tname = data.get(CLASS_TYPE_FIELD)
                if not isinstance(tname, str):
                    return None, [
                        ParseError(
                            path=f"{key_path}.{CLASS_TYPE_FIELD}",
                            expected=__expected(str),
                            comment=CLASS_TYPE_COMMENT,
                        )
                    ]

                parent = ptype

                next_ptype = __get_subclass_from_name(ptype, tname)
                if next_ptype is None:
                    return None, [
                        ParseError(
                            path=f"{key_path}.{CLASS_TYPE_FIELD}",
                            expected=__get_subclass_names(parent),
                            comment=CLASS_TYPE_COMMENT,
                        )
                    ]
                ptype = next_ptype

            type_fields = {}
            for data_field in dataclasses.fields(ptype):
                if data_field.name in data:
                    d, err = __parse_type(
                        ptype=data_field.type,
                        data=data[data_field.name],
                        key_path=f"{key_path}.{data_field.name}",
                        comment=data_field.metadata.get(COMMENT_FIELD_NAME),
                    )
                elif isinstance(
                    data_field.default, dataclasses._MISSING_TYPE
                ) and isinstance(data_field.default_factory, dataclasses._MISSING_TYPE):
                    d, err = None, [
                        ParseError(
                            path=f"{key_path}.{data_field.name}",
                            expected=__expected(data_field.type),
                            comment=comment,
                        )
                    ]
                else:
                    continue

                if err:
                    errors += err
                else:
                    type_fields[data_field.name] = d

            if errors:
                return None, errors

            return ptype(**type_fields), []

    else:
        assert False, f"unsupported {ptype}"

    return None, [
        ParseError(path=key_path, expected=__expected(ptype), comment=comment)
    ]


def parse_track(
    data: typing.Dict[str, typing.Any],
) -> typing.Tuple[typing.Optional[Track], typing.Sequence[ParseError]]:
    if data is None:
        return None, [ParseError("", __expected(Track))]

    return __parse_type(Track, data)
