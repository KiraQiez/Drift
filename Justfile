check: lint typecheck test

setup:
    uv sync --locked

test:
    uv run --locked pytest

format:
    uv run --locked ruff format .

lint:
    uv run --locked ruff check .
    uv run --locked ruff format --check .

typecheck:
    uv run --locked mypy src

build:
    uv build
