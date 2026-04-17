from noctyra.core.Transformer import BaseTransformer
import ast


class Generic(BaseTransformer):
    def generic_visit(self, node: ast.AST) -> ast.AST:

        super().generic_visit(node)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            return node

        result_res = self.eval(node)

        if result_res is not None:
            result = self.unwrap(result_res)
            if isinstance(result, (str, bytes, bool, int, float, complex)):
                return ast.Constant(result)

        return node
