from __future__ import annotations

import argparse
import ast
import sys
import time
from pathlib import Path

import black
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from noctyra.core import TransformerPipeline
from noctyra.transformers import (
    AlgebraicSimplifier,
    BasicAttributes,
    BasicFunctions,
    BasicInliner,
    CollectionsTransformer,
    ConditionSimplifier,
    ConstsTransformer,
    ControlFlowSimplifier,
    DeadCodeRemover,
    FStringTransformer,
    Generic,
    IdentifierRenamer,
    ImportAliasFolder,
    LambdaLP,
    LCTransformer,
    NameReplacer,
)
from noctyra.utils import LOGGER

__version__ = "0.4.0"

BANNER = r"""
 _   _            _                   
| \ | | ___   ___| |_ _   _ _ __ __ _ 
|  \| |/ _ \ / __| __| | | | '__/ _` |
| |\  | (_) | (__| |_| |_| | | | (_| |
|_| \_|\___/ \___|\__|\__, |_|  \__,_|
                      |___/           
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noctyra",
        description="Static Python deobfuscator based on AST transformations.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("file", help="Path to the Python file to transform.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="out.py",
        help="Output file for the transformed code.",
    )
    parser.add_argument(
        "--rename-mode",
        choices=["all", "obfuscated", "none"],
        default="all",
        help="Identifier renaming mode.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Number of iterations to apply (0 = auto until convergence).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum iterations in auto mode.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=50,
        help="Maximum recursion depth during safe evaluation.",
    )
    parser.add_argument(
        "--max-allocation",
        type=int,
        default=100_000,
        help="Maximum allocation size to prevent DoS.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print transformed code to stdout.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress banner, logs, and summary table.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _print_banner(console: Console) -> None:
    title = Text(BANNER.strip("\n"), style="bold cyan")
    subtitle = Text(
        f"v{__version__} • AST-based Python Deobfuscation Pipeline",
        style="dim white",
    )
    console.print(
        Panel.fit(
            Text.assemble(title, "\n", subtitle),
            border_style="bright_magenta",
            padding=(0, 2),
        )
    )


def _print_summary(
    console: Console,
    input_path: Path,
    output_path: Path,
    rename_mode: str,
    orig_code: str,
    new_code: str,
    orig_ast_size: int,
    new_ast_size: int,
    elapsed_ms: float,
) -> None:
    reduction = (
        ((orig_ast_size - new_ast_size) / orig_ast_size * 100.0)
        if orig_ast_size > 0
        else 0.0
    )
    table = Table(
        title="Deobfuscation Summary",
        border_style="cyan",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")

    table.add_row("Input", str(input_path))
    table.add_row("Output", str(output_path))
    table.add_row("Rename Mode", rename_mode)
    table.add_row(
        "Lines",
        f"{len(orig_code.splitlines())} -> {len(new_code.splitlines())}",
    )
    table.add_row(
        "AST Size",
        f"{orig_ast_size} -> {new_ast_size} ({reduction:+.1f}%)",
    )
    table.add_row("Elapsed", f"{elapsed_ms:.1f} ms")

    console.print(table)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    err_console = Console(stderr=True)
    ui_console = Console(stderr=True) if args.stdout else Console()

    if args.quiet:
        LOGGER.setLevel("ERROR")
    elif args.debug:
        LOGGER.setLevel("DEBUG")

    if not args.quiet:
        _print_banner(ui_console)

    input_path = Path(args.file)
    if not input_path.is_file():
        err_console.print(
            Panel(
                f"Input file not found: [bold]{input_path}[/bold]",
                title="Error",
                border_style="red",
            )
        )
        sys.exit(1)

    code = input_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        err_console.print(
            Panel(
                f"Failed to parse [bold]{input_path}[/bold]: {exc}",
                title="SyntaxError",
                border_style="red",
            )
        )
        sys.exit(1)

    orig_ast_size = len(ast.dump(tree))
    start = time.perf_counter()

    pipeline = TransformerPipeline(
        transformers=[
            ImportAliasFolder,
            BasicInliner,
            ConstsTransformer,
            AlgebraicSimplifier,
            CollectionsTransformer,
            BasicFunctions,
            BasicAttributes,
            FStringTransformer,
            LCTransformer,
            ConditionSimplifier,
            ControlFlowSimplifier,
            NameReplacer,
            DeadCodeRemover,
            Generic,
            LambdaLP,
        ],
        iterations=args.iterations,
        max_iterations=args.max_iterations,
        max_depth=args.max_depth,
        max_allocation=args.max_allocation,
    )

    if args.quiet:
        result = pipeline.visit(tree)
        if args.rename_mode != "none":
            result = IdentifierRenamer(mode=args.rename_mode).run(
                result,
                max_depth=args.max_depth,
                max_allocation=args.max_allocation,
            )
    else:
        with ui_console.status(
            "[bold cyan]Running AST deobfuscation pipeline...[/bold cyan]",
            spinner="dots",
        ):
            result = pipeline.visit(tree)
            if args.rename_mode != "none":
                result = IdentifierRenamer(mode=args.rename_mode).run(
                    result,
                    max_depth=args.max_depth,
                    max_allocation=args.max_allocation,
                )

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    new_ast_size = len(ast.dump(result))

    new_code = ast.unparse(result)
    res = black.format_str(new_code, mode=black.Mode())

    output_path = Path(args.output)
    output_path.write_text(res, encoding="utf-8")
    LOGGER.debug(f"Output written to {output_path}")

    if not args.quiet:
        _print_summary(
            ui_console,
            input_path=input_path,
            output_path=output_path,
            rename_mode=args.rename_mode,
            orig_code=code,
            new_code=res,
            orig_ast_size=orig_ast_size,
            new_ast_size=new_ast_size,
            elapsed_ms=elapsed_ms,
        )

    if args.stdout:
        if sys.stdout.isatty():
            Console().print(Syntax(res, "python", theme="monokai", line_numbers=True))
        else:
            print(res, end="")
