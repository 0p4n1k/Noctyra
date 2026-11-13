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

    @staticmethod
    def _should_fold(node: ast.AST, result: object) -> bool:
        if isinstance(result, (list, tuple, set, dict)):
            if len(result) > 16 and len(repr(result)) > len(ast.unparse(node)):
                return False
        return True

    def visit_BinOp(self, node):
        self.generic_visit(node)

        result_res = self.eval(node)

        if result_res is not None:
            result = self.unwrap(result_res)
            if self._should_fold(node, result):
                LOGGER.debug(f"Folded BinOp into constant: {result!r}")
                return ast.Constant(value=result)

        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        result_res = self.eval(node)

        if result_res is not None:
            result = self.unwrap(result_res)
            if self._should_fold(node, result):
                LOGGER.debug(f"Folded UnaryOp into constant: {result!r}")
                return ast.Constant(value=result)

        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)

        result_res = self.eval(node)

        if isinstance(result_res, (type(None), LambdaType, ImportSymbol)):
            return node

        result = self.unwrap(result_res)
        if not self._should_fold(node, result):
            return node

        return ast.Constant(value=result)

    def visit_Subscript(self, node: ast.Subscript):
        self.generic_visit(node)

        result_res = self.eval(node)

        if result_res is None:
            return node

        result = self.unwrap(result_res)
        if not self._should_fold(node, result):
            return node

        return ast.Constant(value=result)
