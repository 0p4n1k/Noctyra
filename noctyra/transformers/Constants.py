from noctyra.core import ImportSymbol, LambdaType
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

        result_res = self.eval(node)

        if result_res is not None:
            result = self.unwrap(result_res)
            LOGGER.debug(f"Folded BinOp into constant: {result!r}")
            return ast.Constant(value=result)

        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        result_res = self.eval(node)

        if result_res is not None:
            result = self.unwrap(result_res)
            LOGGER.debug(f"Folded UnaryOp into constant: {result!r}")
            return ast.Constant(value=result)

        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)

        result_res = self.eval(node)

        if isinstance(result_res, (type(None), LambdaType, ImportSymbol)):
            return node

        return ast.Constant(value=self.unwrap(result_res))

    def visit_Subscript(self, node: ast.Subscript):
        self.generic_visit(node)

        result_res = self.eval(node)

        if result_res is None:
            return node

        return ast.Constant(value=self.unwrap(result_res))
