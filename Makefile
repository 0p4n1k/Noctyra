.PHONY: test lint format typecheck help

help:
	@echo "Noctyra Development Commands"
	@echo "  test       Run unit tests"
	@echo "  lint       Check code style with ruff"
	@echo "  format     Format code with black and ruff"
	@echo "  typecheck  Run mypy type checking"

test:
	uv run pytest tests/

lint:
	uv run ruff check .

format:
	uv run black .
	uv run ruff check . --fix

typecheck:
	uv run mypy . --ignore-missing-imports
