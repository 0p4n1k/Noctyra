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
            value_res = self.eval(node.func.value)

            if value_res is not None:
                value = self.unwrap(value_res)
                args_res = [self.eval(arg) for arg in node.args]

                if any(arg is None for arg in args_res):
                    return node

                args = [self.unwrap(a) for a in args_res]

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
