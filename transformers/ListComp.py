from transformers.BaseTransformer import BaseTransformer
from utils.logger import LOGGER
from classes import Variable
import ast


class LCTransformer(BaseTransformer):

    def visit_ListComp(self, node):
        self.generic_visit(node)

        iterable = self.eval(node.generators[0].iter)

        if not isinstance(iterable, (list, tuple, str, bytes, range)):
            return node

        ifs = node.generators[0].ifs

        target = node.generators[0].target

        if target is None or not isinstance(target, ast.Name):
            return node

        def check(item):
            if ifs:
                return all(
                    self.eval(
                        if_cond,
                        self.ctx.copy_with([Variable(name=target.id, value=item)]),
                    )
                    for if_cond in ifs
                )
            return True

        try:
            result = [
                self.eval(
                    node.elt, self.ctx.copy_with([Variable(name=target.id, value=item)])
                )
                for item in iterable
                if check(item)
            ]
        except Exception as e:
            LOGGER.debug(f"List comprehension evaluation failed: {e}")
            return node

        if all(elem is None for elem in result):
            return node

        LOGGER.debug(f"Folded list comprehension: {len(result)} items")
        return ast.Constant(value=result)  # type: ignore

    def visit_GeneratorExp(self, node: ast.GeneratorExp):

        self.generic_visit(node)

        iterable = self.eval(node.generators[0].iter)

        if not isinstance(iterable, (list, tuple, str, bytes, range)):
            return node

        ifs = node.generators[0].ifs

        target = node.generators[0].target

        if target is None or not isinstance(target, ast.Name):
            return node

        def check(item):
            if ifs:
                return all(
                    self.eval(
                        if_cond,
                        self.ctx.copy_with([Variable(name=target.id, value=item)]),
                    )
                    for if_cond in ifs
                )
            return True

        try:
            result = [
                self.eval(
                    node.elt, self.ctx.copy_with([Variable(name=target.id, value=item)])
                )
                for item in iterable
                if check(item)
            ]
        except Exception as e:
            LOGGER.debug(f"Generator expression evaluation failed: {e}")
            return node

        if all(elem is None for elem in result):
            return node

        LOGGER.debug(f"Folded generator expression into list: {len(result)} items")

        return ast.List(
            elts=[ast.Constant(value=elem) for elem in result], ctx=ast.Load()
        )
