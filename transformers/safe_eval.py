from utils.shared import OPS
import operator
import ast

class SafeEval(ast.NodeVisitor):
    
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
        
    def visit_Constant(self, node: ast.Constant):
        return node.value
    
def safe_eval(node: ast.AST):
    return SafeEval().visit(node)