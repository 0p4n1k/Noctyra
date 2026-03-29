from transformers.safe_eval import safe_eval
from utils.shared import ATTR
from utils.logger import LOGGER
import ast


class BasicAttributes(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)

        if not isinstance(node.func, ast.Attribute):
            return node

        attr_name = node.func.attr

        if attr_name in ATTR:
            value = safe_eval(node.func.value)

            if value is not None:
                args = [safe_eval(arg) for arg in node.args]

                if any(arg is None for arg in args):
                    return node

                try:
                    result = getattr(value, attr_name)(*args)
                    LOGGER.debug(
                        f"Resolved attribute call: {type(value).__name__}.{attr_name} -> {result!r}"
                    )
                    return ast.Constant(value=result)

                except Exception as e:
                    LOGGER.debug(f"Attribute call failed: {e}")
                    pass

        return node
