from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
import ast


class BasicFunctions(BaseTransformer):
    def visit_Expr(self, node: ast.Expr):
        self.generic_visit(node)

        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                if node.value.func.id == "exec":
                    args_res = [self.eval(arg) for arg in node.value.args]

                    if any(i is None for i in args_res):
                        return node

                    args = [self.unwrap(a) for a in args_res]
                    if len(args) == 1 and isinstance(args[0], str | bytes):
                        LOGGER.warning(f"Unrolling exec() call: {args[0]!r}")
                        code = ast.parse(args[0]).body  # type: ignore
                        return [self.generic_visit(nd) for nd in code]

        return node

    def visit_Call(self, node):
        self.generic_visit(node)

        result_res = self.eval(node)

        if result_res is not None:
            result = self.unwrap(result_res)
            LOGGER.debug(f"Folded function call: {ast.unparse(node)} -> {result!r}")
            return ast.Constant(value=result)

        return node
