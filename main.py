from transformers.constants import ConstsTransformer
import ast


def main():
    code = open("original.py").read()
    
    
    tree = ast.parse(code)
    
    result = ConstsTransformer().visit(tree)
    
    new_code = ast.unparse(result)
    
    print(new_code)
    
    
if __name__ == "__main__":
    main()