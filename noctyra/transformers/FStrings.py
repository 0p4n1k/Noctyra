from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
import ast


class FStringTransformer(BaseTransformer):
    """Fold constant and partially-constant f-strings (ast.JoinedStr)."""

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        self.generic_visit(node)

        result_res = self.eval(node)
        if result_res is not None:
            result = self.unwrap(result_res)
            if isinstance(result, str):
                LOGGER.debug(f"Folded f-string into constant: {result!r}")
                return ast.copy_location(ast.Constant(value=result), node)

        merged_values: list[ast.expr] = []
        changed = False

        for item in node.values:
            current: ast.expr = item
            if isinstance(item, ast.FormattedValue):
                item_res = self.eval(item)
                if item_res is not None:
                    item_val = self.unwrap(item_res)
                    if isinstance(item_val, str):
                        current = ast.copy_location(ast.Constant(value=item_val), item)
                        changed = True

            if isinstance(current, ast.Constant) and isinstance(current.value, str):
                if current.value == "":
                    changed = True
                    continue
                if (
                    merged_values
                    and isinstance(merged_values[-1], ast.Constant)
                    and isinstance(merged_values[-1].value, str)
                ):
                    merged_values[-1] = ast.copy_location(
                        ast.Constant(value=merged_values[-1].value + current.value),
                        merged_values[-1],
                    )
                    changed = True
                    continue

            merged_values.append(current)

        if not merged_values:
            return ast.copy_location(ast.Constant(value=""), node)

        if (
            len(merged_values) == 1
            and isinstance(merged_values[0], ast.Constant)
            and isinstance(merged_values[0].value, str)
        ):
            return ast.copy_location(merged_values[0], node)

        if changed:
            LOGGER.debug("Partially folded f-string segments")
            return ast.copy_location(ast.JoinedStr(values=merged_values), node)

        return node
