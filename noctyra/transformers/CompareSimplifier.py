from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import OPS, LOGGER
import ast


class ConditionSimplifier(BaseTransformer):

    def visit_BoolOp(self, node: ast.BoolOp):
        op = OPS.get(type(node.op))

        if op is None:
            return node

        return ast.Constant(op([self.eval(arg) for arg in node.values]))

    def visit_Compare(self, node: ast.Compare):
        left = self.eval(node.left)
        if left is None:
            return node

        results = []

        for op, comparator in zip(node.ops, node.comparators):
            right = self.eval(comparator)
            if right is None:
                return node

            if type(op) in OPS:
                try:
                    result = OPS[type(op)](left, right)
                    results.append(result)
                    left = right
                except Exception as e:
                    LOGGER.debug(f"Comparison failed: {e}")
                    return node

            else:
                return node

        if all(i is not None for i in results):
            final_res = all(results)
            LOGGER.debug(f"Simplified comparison: {final_res}")
            return ast.Constant(value=final_res)

        return node

    def visit_IfExp(self, node: ast.IfExp):

        result = self.eval(node)

        if result:
            return ast.Constant(value=result)

        return node
