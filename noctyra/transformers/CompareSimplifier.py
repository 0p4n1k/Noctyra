from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import COMP_OPS, IMMUTABLE_TYPES, LOGGER
import ast


class ConditionSimplifier(BaseTransformer):

    def visit_BoolOp(self, node: ast.BoolOp):
        self.generic_visit(node)
        is_and = isinstance(node.op, ast.And)
        remaining: list[ast.expr] = []
        last_const: tuple[bool, object] | None = None

        for val in node.values:
            res = self.eval(val)
            if res is None:
                remaining.append(val)
                last_const = None
                continue

            unwrapped = self.unwrap(res)
            truthy = bool(unwrapped)
            short_circuit = (not truthy) if is_and else truthy

            if short_circuit:
                if not remaining and isinstance(unwrapped, IMMUTABLE_TYPES):
                    return ast.copy_location(ast.Constant(value=unwrapped), node)
                const_node: ast.expr = (
                    ast.copy_location(ast.Constant(value=unwrapped), val)
                    if isinstance(unwrapped, IMMUTABLE_TYPES)
                    else val
                )
                remaining.append(const_node)
                last_const = None
                break

            last_const = (isinstance(unwrapped, IMMUTABLE_TYPES), unwrapped)

        if not remaining and last_const is not None and last_const[0]:
            return ast.copy_location(ast.Constant(value=last_const[1]), node)  # type: ignore[arg-type]

        if len(remaining) == 1:
            return remaining[0]

        if remaining and len(remaining) < len(node.values):
            return ast.copy_location(ast.BoolOp(op=node.op, values=remaining), node)

        return node

    def visit_Compare(self, node: ast.Compare):
        self.generic_visit(node)
        left_res = self.eval(node.left)
        if left_res is None:
            return node

        left = self.unwrap(left_res)
        results = []

        for op, comparator in zip(node.ops, node.comparators):
            right_res = self.eval(comparator)
            if right_res is None:
                return node

            right = self.unwrap(right_res)

            op_type = type(op)
            if op_type in COMP_OPS:
                try:
                    result = COMP_OPS[op_type](left, right)
                    results.append(result)
                    left = right
                except Exception as e:
                    LOGGER.debug(f"Comparison failed: {e}")
                    return node

            else:
                return node

        if results and all(i is not None for i in results):
            final_res = all(results)
            LOGGER.debug(f"Simplified comparison: {final_res}")
            return ast.Constant(value=final_res)

        return node

    def visit_IfExp(self, node: ast.IfExp):
        self.generic_visit(node)
        result_res = self.eval(node)

        if result_res is not None:
            return ast.Constant(value=self.unwrap(result_res))

        return node
