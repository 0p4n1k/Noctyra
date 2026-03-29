from transformers import ConstsTransformer, BasicFunctions, BasicAttributes, LCTransformer, ConditionSimplifier
from transformers import TransformerPipeline
from utils.logger import LOGGER
import argparse
import black
import ast


def main():    
    argparser = argparse.ArgumentParser(description="Transform Python code using AST transformers.")
    argparser.add_argument("file", help="Path to the Python file to transform.")
    argparser.add_argument("--iterations", type=int, default=0, help="Number of iterations to apply the transformers. Default is 0 (auto).")
    argparser.add_argument("--max-iterations", type=int, default=100, help="Maximum iterations when using auto mode. Default is 100.")
    argparser.add_argument("--output", type=str, default="out.py", help="Output file for the transformed code. Default is out.py.")
    argparser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = argparser.parse_args()

    if args.debug:
        LOGGER.setLevel("DEBUG")

    with open(args.file, 'r', encoding='utf-8') as f:
        code = f.read()

    tree = ast.parse(code)

    pipeline = TransformerPipeline(transformers=[ConstsTransformer, BasicFunctions, BasicAttributes, LCTransformer, ConditionSimplifier], iterations=args.iterations)
    
    result = pipeline.visit(tree)

    new_code = ast.unparse(result)
    
    res = black.format_str(new_code, mode=black.Mode())
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(res)
        
    LOGGER.debug(f"Output written to {args.output}")

    
if __name__ == "__main__":
    main()