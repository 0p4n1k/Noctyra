from noctyra.core.Transformer import BaseTransformer
import ast


class Generic(BaseTransformer):
    def generic_visit(self, node: ast.AST) -> ast.AST:

        super().generic_visit(node)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            return node

        result = self.eval(node)

        if isinstance(result, (str, bytes, bool, int, float, complex)):
            return ast.Constant(result)

        return node
