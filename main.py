from transformers import (
    ConstsTransformer,
    BasicFunctions,
    BasicAttributes,
    LCTransformer,
    ConditionSimplifier,
    NameReplacer,
    DeadCodeRemover,
)
from transformers import TransformerPipeline
from utils.logger import LOGGER
import argparse
import black
import ast


def main():
    argparser = argparse.ArgumentParser(
        description="Transform Python code using AST transformers."
    )
    argparser.add_argument("file", help="Path to the Python file to transform.")
    argparser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Number of iterations to apply the transformers. Default is 0 (auto).",
    )
    argparser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum iterations when using auto mode. Default is 100.",
    )
    argparser.add_argument(
        "--max-depth",
        type=int,
        default=50,
        help="Maximum depth when inspecting recursive function. Default is 50.",
    )
    argparser.add_argument(
        "--max-allocation",
        type=int,
        default=100_000,
        help="Maximum allocation to prevent DOS. Default is 100000.",
    )
    argparser.add_argument(
        "--output",
        type=str,
        default="out.py",
        help="Output file for the transformed code. Default is out.py.",
    )
    argparser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    argparser.add_argument(
        "--stdout", action="store_true", help="Output transformed code to stdout."
    )

    args = argparser.parse_args()

    if args.debug:
        LOGGER.setLevel("DEBUG")

    with open(args.file, "r", encoding="utf-8") as f:
        code = f.read()

    tree = ast.parse(code)

    pipeline = TransformerPipeline(
        transformers=[
            ConstsTransformer,
            BasicFunctions,
            BasicAttributes,
            LCTransformer,
            ConditionSimplifier,
            NameReplacer,
            DeadCodeRemover,
        ],
        iterations=args.iterations,
        max_iterations=args.max_iterations,
        max_depth=args.max_depth,
        max_allocation=args.max_allocation,
    )

    result = pipeline.visit(tree)

    new_code = ast.unparse(result)

    res = black.format_str(new_code, mode=black.Mode())

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(res)

    LOGGER.debug(f"Output written to {args.output}")

    if args.stdout:
        print(res)


if __name__ == "__main__":
    main()
