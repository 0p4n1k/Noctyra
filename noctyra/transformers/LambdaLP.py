"""
LambdaLP = Lambda Last Pass if safe eval of lambda fail
"""

from noctyra.core.Transformer import BaseTransformer
from noctyra.core import LambdaType, SymbolicValue
from noctyra.core import Context, Variable
from typing import Any
import ast
import copy


class Replacer(BaseTransformer):
    def visit_Name(self, node: ast.Name) -> Any:

        if not self.ctx.has(node.id):
            return node

        res = self.ctx.get(node.id).get()  # type: ignore

        if isinstance(res, SymbolicValue):
            return res.to_ast()

        if isinstance(res, ast.AST):
            return copy.deepcopy(res)

        if isinstance(res, ast.Constant) and isinstance(
            res.value, (int, str, bytes, float, complex, type(None))
        ):
            return res

        return node


class LambdaLP(BaseTransformer):
    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if isinstance(node.func, ast.Lambda):
            func_args = node.func.args
            func_body: ast.AST = node.func.body
            if (
                func_args.vararg is not None
                or func_args.kwarg is not None
                or func_args.posonlyargs
                or func_args.kwonlyargs
                or any(isinstance(a, ast.Starred) for a in node.args)
            ):
                return node
        elif isinstance(node.func, ast.Name) and self.ctx.has(node.func.id):
            func = self.ctx.get(node.func.id).get()  # type: ignore
            if not isinstance(func, LambdaType):
                return node
            func_args = func.get_args()
            func_body = func.get_body()
        else:
            return node

        mapping_dict = {}

        for i, arg_value in enumerate(node.args):
            if i < len(func_args.args):
                arg_name = func_args.args[i].arg
                mapping_dict[arg_name] = Variable(arg_name, arg_value)  # type: ignore

        for kw in node.keywords:
            if kw.arg is None:  # TODO: support **kwargs
                continue

            mapping_dict[kw.arg] = Variable(kw.arg, kw.value)  # type: ignore

        result = Replacer().run(
            copy.deepcopy(func_body),
            ctx=Context(list(mapping_dict.values())),
        )

        return result
