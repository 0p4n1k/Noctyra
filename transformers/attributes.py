from transformers.safe_eval import safe_eval
from utils.shared import ATTR
import ast



class BasicAttributes(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        
        if not isinstance(node.func, ast.Attribute):
            return node
        
        attr_name = node.func.attr
        
        if attr_name in ATTR:
            value = safe_eval(node.func.value)

            if value is not None:
                attr_value = ATTR[attr_name]
                try:
                    result = attr_value(value)
                    return ast.Constant(value=result)
                
                except Exception as e:
                    print(f"Error evaluating attribute {attr_name} on value {value}: {e}")
        
        return node