from noctyra.core import is_symbolic_ref, to_node
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
from typing import Any
import ast


class ConstsTransformer(BaseTransformer):
    @staticmethod
    def _should_fold(node: ast.AST, result: object) -> bool:
        if isinstance(result, (list, tuple, set, dict)):
            if len(result) > 16 and len(repr(result)) > len(ast.unparse(node)):
                return False
        return True

    def _fold_node(self, node: ast.AST, result_res: Any) -> ast.AST:
        if result_res is None or is_symbolic_ref(result_res):
            return node

        result = self.unwrap(result_res)
        if not self._should_fold(node, result):
            return node

        folded = to_node(result)
        if folded is None:
            return node

        return ast.copy_location(folded, node)

    def visit_BinOp(self, node):
        self.generic_visit(node)

        result_res = self.eval(node)
        folded = self._fold_node(node, result_res)
        if folded is not node:
            LOGGER.debug(f"Folded BinOp into constant: {self.unwrap(result_res)!r}")
        return folded

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        result_res = self.eval(node)
        folded = self._fold_node(node, result_res)
        if folded is not node:
            LOGGER.debug(f"Folded UnaryOp into constant: {self.unwrap(result_res)!r}")
        return folded

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)

        if (
            isinstance(node.func, ast.Name)
            and node.func.id in ("map", "zip", "range")
            and self._is_builtin_usable(node.func.id)
        ):
            return node

        result_res = self.eval(node)
        return self._fold_node(node, result_res)

    def visit_Subscript(self, node: ast.Subscript):
        self.generic_visit(node)

        if not isinstance(node.ctx, ast.Load):
            return node

        result_res = self.eval(node)
        return self._fold_node(node, result_res)
