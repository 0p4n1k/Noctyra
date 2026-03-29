from transformers.safe_eval import safe_eval
from utils.shared import encoding
from utils.logger import LOGGER
import ast


class ConstsTransformer(ast.NodeTransformer):
    def get_module_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        else:
            return None

    def visit_BinOp(self, node):
        self.generic_visit(node)

        result = safe_eval(node)

        if result is not None:
            LOGGER.debug(f"Folded BinOp into constant: {result!r}")
            return ast.Constant(value=result)

        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)

        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            module_name = self.get_module_name(node.func.value)

            if module_name in encoding and func_name in encoding[module_name]:
                func = encoding[module_name][func_name]
                args = [safe_eval(arg) for arg in node.args]

                if any(arg is None for arg in args):
                    return node

                try:
                    result = func(*args)
                    LOGGER.debug(
                        f"Resolved encoding call: {module_name}.{func_name} -> {result!r}"
                    )
                    return ast.Constant(value=result)  # type: ignore
                except Exception as e:
                    LOGGER.debug(f"Failed to resolve encoding call: {e}")

        return node
