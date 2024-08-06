import sys
import tempfile

from ctf_builder.cli import cli


def test() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        sys.argv = ["ctf", "doc", "-o", temp_dir]

        assert cli() == 0
