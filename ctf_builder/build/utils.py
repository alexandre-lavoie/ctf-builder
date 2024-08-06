import typing

T = typing.TypeVar("T")


def subclass_get(cls: typing.Type[T], obj: typing.Any) -> typing.Type[T]:
    for subclass in cls.__subclasses__():
        orig_bases = getattr(subclass, "__orig_bases__", None)
        assert orig_bases

        parent_type_generic = orig_bases[0]
        parent_type_args = typing.get_args(parent_type_generic)
        assert parent_type_args

        if isinstance(obj, parent_type_args[0]):
            return subclass

    assert False, f"unhandled {type(obj)}"


def to_docker_tag(text: str) -> str:
    return text.replace(" ", "_").lower()
