import typing

T = typing.TypeVar("T")
U = typing.TypeVar("U")
def subclass_get(cls: typing.Type[T], obj: U) -> typing.Type[T]:
    for subclass in cls.__subclasses__():
        if subclass.__type__() == type(obj):
            return subclass
    else:
        return None
