#!/bin/sh

isort --check . || exit 1
black --check . || exit 1
mypy . || exit 1
pytest . || exit 1
