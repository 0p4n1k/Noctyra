from ast import FunctionDef, Return
import ast

from noctyra.core.Transformer import BaseTransformer


class DeadCodeRemover(BaseTransformer):
    active = True

    def visit_If(self, node):
        self.generic_visit(node)

        test_value = self.eval(node.test)

        if test_value is True:
            return node.body
        elif test_value is False:
            return node.orelse

        return node

    def visit_FunctionDef(self, node: FunctionDef):

        self.generic_visit(node)

        new_body: list[ast.stmt] = []
        for stmt in node.body:
            new_body.append(stmt)

            if isinstance(stmt, Return):
                break

        node.body = new_body
        return node
