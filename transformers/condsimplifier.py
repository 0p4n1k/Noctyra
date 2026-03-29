from transformers.safe_eval import safe_eval
from utils.shared import OPS
from utils.logger import LOGGER
import ast



class ConditionSimplifier(ast.NodeTransformer):

    def visit_Compare(self, node: ast.Compare):

        left = safe_eval(node.left)

        if left is None:
            return node

        results = []

        for op, comparator in zip(node.ops, node.comparators):
            right = safe_eval(comparator)
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