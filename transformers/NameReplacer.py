from transformers.BaseTransformer import BaseTransformer
from utils.logger import LOGGER
import ast


class NameReplacer(BaseTransformer):
    def visit_Name(self, node):
        self.generic_visit(node)

        if isinstance(node.ctx, ast.Store):
            return node

        result = self.eval(node)
        if result is not None:
            LOGGER.debug(f"Resolved variable: {node.id} -> {result!r}")
            return ast.Constant(value=result)

        return node
