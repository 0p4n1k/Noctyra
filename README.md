# Noctyra

![Noctyra Demo](assets/demo.gif)

[![PyPI version](https://img.shields.io/pypi/v/noctyra)](https://pypi.org/project/noctyra/)
[![Python versions](https://img.shields.io/pypi/pyversions/noctyra)](https://pypi.org/project/noctyra/)
[![Downloads](https://img.shields.io/pypi/dm/noctyra)](https://pypi.org/project/noctyra/)
[![License](https://img.shields.io/pypi/l/noctyra)](https://pypi.org/project/noctyra/)

Noctyra is an AST-based framework designed for code transformation and deobfuscation. It provides a modular pipeline to analyze and simplify Python source code by resolving complex expressions and logic.

## Overview

The project aims to provide a flexible environment for processing Python's Abstract Syntax Tree. By employing a sequence of pluggable transformers, Noctyra can:

- Simplify nested logic and conditions.
- Resolve static values and common encoding patterns.
- Unroll dynamic execution blocks into readable code.
- Optimize and clean up obfuscated constructs.

## Getting Started

### Prerequisites

Ensure you have `uv` installed for dependency management.

```bash
uv sync
```

### Running the Pipeline

To process a target script, use the following command:

```bash
python main.py <input_file> [options]
```

**Options:**
- `file`: Path to the input Python file (required).
- `--output`: File name for the transformed code (default: `out.py`).
- `--iterations`: Set a fixed number of transformation passes (default: `0` for auto-detect).
- `--max-iterations`: Limit the passes in auto mode (default: `100`).
- `--debug`: Enable verbose logging for debugging transformations. (look sick)

## Development

This project uses `uv` for dependency management and a `Makefile` for common tasks.

### Setup
```bash
uv sync --all-extras --dev
```

### Quality Control
Before submitting a PR or pushing changes, ensure all checks pass:

- **Run Tests**: `make test`
- **Lint & Format**: `make format`
- **Type Check**: `make typecheck`

*(Windows users: These commands work automatically via `make.bat`.)*

### CI/CD
Automated checks are performed on every push via GitHub Actions, including linting with Ruff, type checking with Mypy, and unit testing with Pytest.

## Security Notice

Noctyra includes an internal evaluation engine with basic resource limits. However, when dealing with untrusted code, it is highly recommended to run the pipeline within an isolated environment (such as a container or sandbox) to prevent potential side effects or resource exhaustion.

---