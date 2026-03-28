from transformers.safe_eval import safe_eval
from utils.shared import FUNCS
import ast



class BasicFunctions(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        
        if isinstance(node.func, ast.Name):
            if node.func.id in FUNCS:
                func = FUNCS[node.func.id]
                args = [safe_eval(arg) for arg in node.args]
                
                if any(arg is None for arg in args):
                    return node
                
                return ast.Constant(value=func(*args)) #type: ignore
            
        return node