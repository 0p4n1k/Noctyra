from transformers.safe_eval import safe_eval
import ast

class LCTransformer(ast.NodeTransformer):
    
    
    def visit_ListComp(self, node):
        self.generic_visit(node)

        iterable = safe_eval(node.generators[0].iter)
        
        if iterable is None:
            return node
        print(ast.dump(node, indent=4))
        result = [safe_eval(node.elt, {node.generators[0].target.id: item}) for item in iterable]

        if result is None:
            return node
        
        return ast.List(elts=result, ctx=ast.Load())