import logging
import sys

LOG = logging.getLogger("ctf_builder")


class InfoFilter(logging.Filter):
    def filter(self, rec):
        return rec.levelno in (logging.DEBUG, logging.INFO)


def setup_logging(logger: logging.Logger, verbose: bool) -> None:
    logger.setLevel(logging.DEBUG if verbose else logging.WARN)
    logger.propagate = False

    formatter = logging.Formatter("%(message)s")

    if verbose:
        stdout_stream = logging.StreamHandler(sys.stdout)
        stdout_stream.setLevel(logging.DEBUG)
        stdout_stream.setFormatter(formatter)
        stdout_stream.addFilter(InfoFilter())
        logger.addHandler(stdout_stream)

    stderr_stream = logging.StreamHandler(sys.stderr)
    stderr_stream.setLevel(logging.WARN)
    stderr_stream.setFormatter(formatter)
    logger.addHandler(stderr_stream)
