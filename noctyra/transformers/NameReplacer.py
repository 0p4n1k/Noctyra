from noctyra.core.Transformer import BaseTransformer
from noctyra.core import CustomFunction
from noctyra.utils import LOGGER
import ast


class NameReplacer(BaseTransformer):
    def visit_Name(self, node):
        self.generic_visit(node)

        if isinstance(node.ctx, ast.Store):
            return node

        result = self.eval(node)
        if result is not None and not isinstance(result, CustomFunction):
            LOGGER.debug(f"Resolved variable: {node.id} -> {result!r}")
            return ast.Constant(value=result)

        return node
