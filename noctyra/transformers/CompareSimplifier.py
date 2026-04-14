from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import COMP_OPS, LOGGER
import ast


class ConditionSimplifier(BaseTransformer):

    def visit_BoolOp(self, node: ast.BoolOp):
        self.generic_visit(node)
        values = [self.eval(arg) for arg in node.values]

        if any(v is None for v in values):
            return node

        if isinstance(node.op, ast.And):
            return ast.Constant(value=all(values))
        elif isinstance(node.op, ast.Or):
            return ast.Constant(value=any(values))

        return node

    def visit_Compare(self, node: ast.Compare):
        self.generic_visit(node)
        left = self.eval(node.left)
        if left is None:
            return node

        results = []

        for op, comparator in zip(node.ops, node.comparators):
            right = self.eval(comparator)
            if right is None:
                return node

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
        result = self.eval(node)

        if result is not None:
            return ast.Constant(value=result)

        return node
