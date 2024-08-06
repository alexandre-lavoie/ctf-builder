#!/bin/sh

black --check **/*.py || exit 1
mypy --disable-error-code=import-untyped -p ctf_builder -p tests || exit 1
pytest || exit 1