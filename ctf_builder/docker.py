import typing


def to_docker_tag(text: str, repository: typing.Optional[str] = None) -> str:
    tag = text.replace(" ", "-").lower()

    if repository:
        tag = repository.rstrip("/ ") + "/" + tag

    return tag
