from transformers.safe_eval import safe_eval
from utils.logger import LOGGER
import ast

class LCTransformer(ast.NodeTransformer):


    def visit_ListComp(self, node):
        self.generic_visit(node)

        iterable = safe_eval(node.generators[0].iter)

        if iterable is None:
            return node


        ifs = node.generators[0].ifs

        if node.generators[0].target is None or not isinstance(node.generators[0].target, ast.Name):
            return node

        verif = lambda item: all(safe_eval(if_cond, {node.generators[0].target.id: item}) for if_cond in ifs) if ifs else lambda item: True

        try:
            result = [
                safe_eval(node.elt, {node.generators[0].target.id: item})
                for item in iterable
                if verif(item)
            ]
        except Exception as e:
            LOGGER.debug(f"List comprehension evaluation failed: {e}")
            return node



        if all(elem is None for elem in result):
            return node


        LOGGER.debug(f"Folded list comprehension: {len(result)} items")
        return ast.Constant(value=result)

    def visit_GeneratorExp(self, node: ast.GeneratorExp):

        self.generic_visit(node)

        iterable = safe_eval(node.generators[0].iter)

        if iterable is None:
            return node


        ifs = node.generators[0].ifs

        if node.generators[0].target is None or not isinstance(node.generators[0].target, ast.Name):
            return node

        verif = lambda item: all(safe_eval(if_cond, {node.generators[0].target.id: item}) for if_cond in ifs) if ifs else True

        try:
            result = [
                safe_eval(node.elt, {node.generators[0].target.id: item})
                for item in iterable
                if verif(item)
            ]
        except Exception as e:
            LOGGER.debug(f"Generator expression evaluation failed: {e}")
            return node


        if all(elem is None for elem in result):
            return node


        LOGGER.debug(f"Folded generator expression into list: {len(result)} items")
        return ast.Constant(value=result)