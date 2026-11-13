"""
LambdaLP = Lambda Last Pass if safe eval of lambda fail
"""

from noctyra.core.Transformer import BaseTransformer
from noctyra.core import Context, LambdaType, SymbolicValue, Variable
from noctyra.utils.Shared import is_pure_expr
from typing import Any, cast
import ast
import copy


def _collect_bound_names_in_expr(node: ast.AST) -> set[str]:
    """Return parameter/target names introduced by inner lambdas or comprehensions."""
    bound: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Lambda):
            for a in (
                list(child.args.posonlyargs)
                + list(child.args.args)
                + list(child.args.kwonlyargs)
            ):
                bound.add(a.arg)
            if child.args.vararg is not None:
                bound.add(child.args.vararg.arg)
            if child.args.kwarg is not None:
                bound.add(child.args.kwarg.arg)
        elif isinstance(child, ast.comprehension):
            for target_child in ast.walk(child.target):
                if isinstance(target_child, ast.Name):
                    bound.add(target_child.id)
    return bound


def _collect_loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _count_param_uses(body: ast.AST, params: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {p: 0 for p in params}

    def walk(node: ast.AST, shadowed: set[str]) -> None:
        if isinstance(node, ast.Name):
            if (
                isinstance(node.ctx, ast.Load)
                and node.id in counts
                and node.id not in shadowed
            ):
                counts[node.id] += 1
            return
        if isinstance(node, ast.Lambda):
            for d in node.args.defaults:
                walk(d, shadowed)
            for kd in node.args.kw_defaults:
                if kd is not None:
                    walk(kd, shadowed)
            inner_shadow = set(shadowed)
            for a in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            ):
                inner_shadow.add(a.arg)
            if node.args.vararg is not None:
                inner_shadow.add(node.args.vararg.arg)
            if node.args.kwarg is not None:
                inner_shadow.add(node.args.kwarg.arg)
            walk(node.body, inner_shadow)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            if node.generators:
                walk(node.generators[0].iter, shadowed)
            inner_shadow = set(shadowed)
            for idx, gen in enumerate(node.generators):
                if idx > 0:
                    walk(gen.iter, inner_shadow)
                for tc in ast.walk(gen.target):
                    if isinstance(tc, ast.Name):
                        inner_shadow.add(tc.id)
                for if_expr in gen.ifs:
                    walk(if_expr, inner_shadow)
            if isinstance(node, ast.DictComp):
                walk(node.key, inner_shadow)
                if node.value is not None:
                    walk(node.value, inner_shadow)
            else:
                walk(node.elt, inner_shadow)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, shadowed)

    walk(body, set())
    return counts


class Replacer(BaseTransformer):
    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        node.args.defaults = [self.visit(d) for d in node.args.defaults]
        node.args.kw_defaults = [
            self.visit(d) if d is not None else None for d in node.args.kw_defaults
        ]
        old_ctx = self.ctx
        self.ctx = Context(parent=old_ctx)
        for a in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        ):
            self.ctx.invalidate(a.arg)
        if node.args.vararg is not None:
            self.ctx.invalidate(node.args.vararg.arg)
        if node.args.kwarg is not None:
            self.ctx.invalidate(node.args.kwarg.arg)
        node.body = self.visit(node.body)
        self.ctx = old_ctx
        return node

    def visit_Name(self, node: ast.Name) -> Any:
        if not isinstance(node.ctx, ast.Load):
            return node

        entry = self.ctx.get(node.id)
        if entry is None:
            return node

        res = entry.get()

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
        elif isinstance(node.func, ast.Name) and self.ctx.has(node.func.id):
            entry = self.ctx.get(node.func.id)
            func = entry.get() if entry is not None else None
            if not isinstance(func, LambdaType):
                return node
            func_args = func.get_args()
            func_body = func.get_body()
        else:
            return node

        if (
            func_args.vararg is not None
            or func_args.kwarg is not None
            or func_args.posonlyargs
            or func_args.kwonlyargs
            or any(isinstance(a, ast.Starred) for a in node.args)
            or any(kw.arg is None for kw in node.keywords)
        ):
            return node

        param_names = [a.arg for a in func_args.args]
        if len(node.args) > len(param_names):
            return node

        bound_exprs: dict[str, ast.expr] = {}
        for i, arg_value in enumerate(node.args):
            bound_exprs[param_names[i]] = arg_value

        for kw in node.keywords:
            assert kw.arg is not None
            if kw.arg not in param_names or kw.arg in bound_exprs:
                return node
            bound_exprs[kw.arg] = kw.value

        default_start = len(param_names) - len(func_args.defaults)
        for idx, pname in enumerate(param_names):
            if pname not in bound_exprs:
                if idx < default_start:
                    return node
                bound_exprs[pname] = func_args.defaults[idx - default_start]

        inner_bound = _collect_bound_names_in_expr(func_body)
        uses = _count_param_uses(func_body, set(bound_exprs))
        for pname, arg_expr in bound_exprs.items():
            if uses.get(pname, 0) != 1 and not is_pure_expr(arg_expr):
                return node
            if _collect_loaded_names(arg_expr) & inner_bound:
                return node

        mapping_vars = [Variable(k, cast(Any, v)) for k, v in bound_exprs.items()]
        return Replacer().run(
            copy.deepcopy(func_body),
            ctx=Context(mapping_vars),
        )
