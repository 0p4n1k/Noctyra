from transformers.safe_eval import safe_eval
from utils.logger import LOGGER
import ast


class BasicFunctions(ast.NodeTransformer):
    def visit_Expr(self, node: ast.Expr):

        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                if node.value.func.id == "exec":
                    args = [safe_eval(arg) for arg in node.value.args]

                    if any(i is None for i in args):
                        return node

                    if len(args) == 1:
                        LOGGER.debug("Unrolling exec() call")
                        return ast.parse(args[0]).body  # type: ignore

        return node

    def visit_Call(self, node):
        self.generic_visit(node)

        result = safe_eval(node)

        if result is not None:
            LOGGER.debug(f"Folded function call: {ast.unparse(node)} -> {result!r}")
            return ast.Constant(value=result)

        return node
