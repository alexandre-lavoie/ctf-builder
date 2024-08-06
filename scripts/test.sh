#!/bin/sh

black --check . || exit 1
mypy . || exit 1
pytest . || exit 1
