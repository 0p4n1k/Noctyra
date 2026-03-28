from transformers import ConstsTransformer, BasicFunctions, BasicAttributes, LCTransformer
from transformers import TransformerPipeline
import black
import ast


def main():
    
    
    
    code = open("original.py", 'rb').read()
    
    tree = ast.parse(code)

    pipeline = TransformerPipeline(transformers=[ConstsTransformer, BasicFunctions, BasicAttributes, LCTransformer])
    
    result = pipeline.visit(tree)

    new_code = ast.unparse(result)
    
    res = black.format_str(new_code, mode=black.Mode())
    
    with open("transformed.py", 'w', encoding='utf-8') as f:
        f.write(res)
    
    # print(res)
    
    
if __name__ == "__main__":
    main()