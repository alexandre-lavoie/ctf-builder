import typing

from ..schema import FileMap


class BuildFileMap:
    @classmethod
    def build(cls, file_map: FileMap) -> typing.Tuple[str, str]:
        return (file_map.source.value, file_map.destination.value)
