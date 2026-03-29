@echo off
if "%1"=="test" (
    uv run pytest tests/
    exit /b %ERRORLEVEL%
) else if "%1"=="lint" (
    uv run ruff check .
    exit /b %ERRORLEVEL%
) else if "%1"=="format" (
    uv run ruff format .
    uv run ruff check . --fix
    exit /b %ERRORLEVEL%
) else if "%1"=="typecheck" (
    uv run mypy . --ignore-missing-imports
    exit /b %ERRORLEVEL%
) else (
    echo Noctyra Development Commands (Windows)
    echo   make test       - Run unit tests
    echo   make lint       - Check code style with ruff
    echo   make format     - Format code with ruff
    echo   make typecheck  - Run mypy type checking
)
