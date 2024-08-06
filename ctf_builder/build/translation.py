import abc
import typing

from ..schema import Translation, TranslationEnglish, TranslationFrench

from .utils import subclass_get


T = typing.TypeVar("T", bound=Translation)


class BuildTranslation(typing.Generic[T], abc.ABC):
    @classmethod
    def get(cls, obj: Translation) -> typing.Type["BuildTranslation"]:
        return subclass_get(cls, obj)

    @classmethod
    @abc.abstractmethod
    def priority(cls) -> int:
        pass

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, translation: T) -> typing.Optional[str]:
        pass

    @classmethod
    def build_common(cls, root: str, translation: Translation) -> typing.Optional[str]:
        path = translation.path.resolve(root)
        if path is None:
            return None

        with open(path) as h:
            return h.read().strip()


class BuildTranslationFrench(BuildTranslation[TranslationFrench]):
    @classmethod
    def priority(cls) -> int:
        return 1

    @classmethod
    def build(cls, root: str, translation: TranslationFrench) -> typing.Optional[str]:
        return cls.build_common(root, translation)


class BuildTranslationEnglish(BuildTranslation[TranslationEnglish]):
    @classmethod
    def priority(cls) -> int:
        return 2

    @classmethod
    def build(cls, root: str, translation: TranslationEnglish) -> typing.Optional[str]:
        return cls.build_common(root, translation)
