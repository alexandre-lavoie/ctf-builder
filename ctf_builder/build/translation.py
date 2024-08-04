import abc
import typing

from ..schema import Translation, TranslationEnglish, TranslationFrench

from .utils import subclass_get

class BuildTranslation(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def __type__(cls) -> typing.Type[Translation]:
        return None
    
    @classmethod
    def get(cls, obj: Translation) -> typing.Optional[typing.Type["BuildTranslation"]]:
        return subclass_get(cls, obj)
    
    @classmethod
    @abc.abstractmethod
    def priority(cls) -> int:
        return 0

    @classmethod
    @abc.abstractmethod
    def build(cls, root: str, translation: Translation) -> typing.Optional[str]:
        return []
    
    @classmethod
    def build_common(cls, root: str, translation: Translation) -> typing.Optional[str]:
        path = translation.path.resolve(root)
        if path is None:
            return False
        
        with open(path) as h:
            return h.read().strip()

class BuildTranslationFrench(BuildTranslation):
    @classmethod
    def __type__(cls) -> typing.Type[Translation]:
        return TranslationFrench

    @classmethod
    def priority(cls) -> int:
        return 1

    @classmethod
    def build(cls, root: str, description: TranslationFrench) -> typing.Optional[str]:
        return cls.build_common(root, description)

class BuildTranslationEnglish(BuildTranslation):
    @classmethod
    def __type__(cls) -> typing.Type[Translation]:
        return TranslationEnglish

    @classmethod
    def priority(cls) -> int:
        return 2

    @classmethod
    def build(cls, root: str, description: TranslationEnglish) -> typing.Optional[str]:
        return cls.build_common(root, description)
