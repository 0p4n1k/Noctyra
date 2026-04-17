"""
LambdaLP = Lambda Last Pass if safe eval of lambda fail
"""

from noctyra.core.Transformer import BaseTransformer
from noctyra.core import LambdaType, SymbolicValue
from noctyra.core import Context, Variable
from typing import Any
import ast


class Replacer(BaseTransformer):
    def visit_Name(self, node: ast.Name) -> Any:

        if not self.ctx.has(node.id):
            return node

        res = self.ctx.get(node.id).get()  # type: ignore

        if isinstance(res, SymbolicValue):
            return res.to_ast()

        if isinstance(res, ast.AST):
            ...

        if isinstance(res, ast.Constant) and isinstance(
            res.value, (int, str, bytes, float, complex, type(None))
        ):
            return res

        return node


class LambdaLP(BaseTransformer):
    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name) or not self.ctx.has(node.func.id):
            return node

        func = self.ctx.get(node.func.id).get()  # type: ignore
        if not isinstance(func, LambdaType):
            return node

        mapping_dict = {}

        for i, arg_value in enumerate(node.args):
            if i < len(func.get_args().args):
                arg_name = func.get_args().args[i].arg
                mapping_dict[arg_name] = Variable(arg_name, arg_value)  # type: ignore

        for kw in node.keywords:
            if kw.arg is None:  # TODO: support **kwargs
                continue

            mapping_dict[kw.arg] = Variable(kw.arg, kw.value)  # type: ignore

        result = Replacer().run(
            func.get_body(),
            ctx=Context(list(mapping_dict.values())),
        )

        return result
