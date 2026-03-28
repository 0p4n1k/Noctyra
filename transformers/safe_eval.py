from utils.shared import ATTR, OPS, FUNCS
import operator
import ast

class SafeEval(ast.NodeVisitor):
    
    def __init__(self, known_vars: dict | None = None) -> None:
        super().__init__()
        self.known_vars = known_vars or {}
    
    def get_name(self, name: str):
        return self.known_vars.get(name)
    
    
    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        
        if visitor == self.generic_visit:
            return None
        
        return visitor(node)
    
    def visit_BinOp(self, node):
        left = self.visit(node.left)      
        right = self.visit(node.right)
        
        if right is None or left is None:
            return None
        
        op = OPS.get(type(node.op))
        
        if op is operator.truediv and right == 0:
            return None
        
        if op is None:
            raise ValueError(f"Unsupported operation: {type(node.op).__name__}")
        
        return op(left, right)
    
    def visit_BoolOp(self, node: ast.BoolOp):
        return all(self.visit(value) for value in node.values) if isinstance(node.op, ast.And) else any(self.visit(value) for value in node.values)
    

    
    def visit_Call(self, node: ast.Call):
        
        
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in FUNCS:
                func = FUNCS[func_name]
                
                args = [self.visit(arg) for arg in node.args]
                if any(arg is None for arg in args):
                    return None
                
                return func(*args)
            
        if isinstance(node.func, ast.Attribute):
            
            attr_name = node.func.attr
            
            if attr_name in ATTR:
                value = self.visit(node.func.value)

                if value is not None:
                    attr_value = ATTR[attr_name]
                    try:
                        result = attr_value(value)
                        return result
                    
                    except Exception:
                        pass
        
        return None
    
    def visit_Constant(self, node: ast.Constant):
        return node.value
    
    def visit_Name(self, node: ast.Name):
        return self.get_name(node.id)
    
    def visit_List(self, node: ast.List):
        return [self.visit(elt) for elt in node.elts]
    
    def visit_IfExp(self, node: ast.IfExp):

        cond = self.visit(node.test)

        if cond is None:
            return None
        
        result = self.visit(node.body) if cond else self.visit(node.orelse)
        return result
    
    def visit_Attribute(self, node: ast.Attribute):

        return getattr(self.visit(node.value), node.attr, None)
    
    def visit_Compare(self, node: ast.Compare):
        
        result = all(OPS.get(type(op), lambda a, b: None)(self.visit(node.left), self.visit(node.comparators[i])) for i, op in enumerate(node.ops))

        return result
    
    
def safe_eval(node: ast.AST, known_vars: dict | None = None):
    
    return SafeEval(known_vars).visit(node)