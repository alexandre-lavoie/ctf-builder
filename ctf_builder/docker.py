def to_docker_tag(text: str) -> str:
    return text.replace(" ", "-").lower()
