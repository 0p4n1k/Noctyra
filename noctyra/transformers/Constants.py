from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
import ast


class ConstsTransformer(BaseTransformer):
    def get_module_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        else:
            return None

    def visit_BinOp(self, node):
        self.generic_visit(node)

        result = self.eval(node)

        if result is not None:
            LOGGER.debug(f"Folded BinOp into constant: {result!r}")
            return ast.Constant(value=result)

        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)

        result = self.eval(node)

        if result is not None:
            LOGGER.debug(f"Folded UnaryOp into constant: {result!r}")
            return ast.Constant(value=result)

        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)

        result = self.eval(node)

        if result is None:
            return node

        return ast.Constant(result)

    def visit_Subscript(self, node: ast.Subscript):
        self.generic_visit(node)

        result = self.eval(node)

        if result is None:
            return node

        return ast.Constant(result)
