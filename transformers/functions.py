from transformers.safe_eval import safe_eval
from utils.shared import FUNCS
import ast



class BasicFunctions(ast.NodeTransformer):
    
    def visit_Expr(self, node: ast.Expr) -> ast.Any:
        
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                if node.value.func.id == 'exec':
                    args = [safe_eval(arg) for arg in node.value.args]
                    if len(args) == 1:
                        return ast.parse(args[0]).body
            
        return node
    
    def visit_Call(self, node):
        self.generic_visit(node)
        
        result = safe_eval(node)

        if result is not None:
            return ast.Constant(value=result)
        
        

        return node