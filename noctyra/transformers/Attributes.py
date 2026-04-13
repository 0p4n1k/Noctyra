from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import ATTR, LOGGER
import ast


class BasicAttributes(BaseTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)

        if not isinstance(node.func, ast.Attribute):
            return node

        attr_name = node.func.attr

        if attr_name in ATTR:
            value = self.eval(node.func.value)

            if value is not None:
                args = [self.eval(arg) for arg in node.args]

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
