from transformers import ConstsTransformer, BasicFunctions, BasicAttributes, LCTransformer
from transformers import TransformerPipeline
import black
import ast


def main():
    
    
    
    code = open("original.py").read()
    
    tree = ast.parse(code)
    print(ast.dump(tree, indent=4))
    
    pipeline = TransformerPipeline(transformers=[ConstsTransformer, BasicFunctions, BasicAttributes, LCTransformer], iterations=1)
    
    result = pipeline.visit(tree)
    
    new_code = ast.unparse(result)
    
    # print(black.format_str(new_code, mode=black.Mode()))
    
    
if __name__ == "__main__":
    main()