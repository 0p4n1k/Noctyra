@echo off
if "%1"=="test" (
    uv run pytest tests/
) else if "%1"=="lint" (
    uv run ruff check .
) else if "%1"=="format" (
    uv run ruff format .
    uv run ruff check . --fix
) else if "%1"=="typecheck" (
    uv run mypy . --ignore-missing-imports
) else (
    echo Noctyra Development Commands (Windows)
    echo   make test       - Run unit tests
    echo   make lint       - Check code style with ruff
    echo   make format     - Format code with ruff
    echo   make typecheck  - Run mypy type checking
)
