from __future__ import annotations

import ast
import keyword
from typing import Any

from noctyra.core import is_symbolic_ref
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _is_pure_fallback(expr: ast.AST) -> bool:
    if isinstance(expr, (ast.Constant, ast.Name, ast.Lambda)):
        return True
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return not any(isinstance(e, ast.Starred) for e in expr.elts) and all(
            _is_pure_fallback(e) for e in expr.elts
        )
    if isinstance(expr, ast.Dict):
        return all(
            k is not None and _is_pure_fallback(k) and _is_pure_fallback(v)
            for k, v in zip(expr.keys, expr.values)
        )
    return False


class GlobalsDispatchSimplifier(BaseTransformer):
    """Simplify reflective globals().items() dispatch comprehensions to direct calls."""

    def __init__(self) -> None:
        super().__init__()
        self._module_bindings: set[str] = set()
        self._func_locals_stack: list[set[str]] = []

    def _collect_module_bindings(self, stmts: list[ast.stmt]) -> set[str]:
        bindings: set[str] = set()
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bindings.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    bindings.update(self._collect_target_names(t))
            elif isinstance(stmt, ast.AnnAssign):
                if stmt.value is not None:
                    bindings.update(self._collect_target_names(stmt.target))
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    bindings.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    if alias.name != "*":
                        bindings.add(alias.asname or alias.name)
            for field_name in ("body", "orelse", "finalbody"):
                sub = getattr(stmt, field_name, None)
                if isinstance(sub, list) and not isinstance(
                    stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    bindings.update(self._collect_module_bindings(sub))
        return bindings

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self._module_bindings = self._collect_module_bindings(node.body)
        self._func_locals_stack = []
        result = self.generic_visit(node)
        ast.fix_missing_locations(result)
        return result

    def visit_Delete(self, node: ast.Delete) -> Any:
        self.generic_visit(node)
        for target in node.targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Del):
                    if not any(
                        child.id in locals_set
                        for locals_set in self._func_locals_stack
                    ):
                        self._module_bindings.discard(child.id)
        return node

    def _def_visit(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Any:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local_names = self._collect_func_locals(node)
            self._func_locals_stack.append(local_names)
            try:
                return super()._def_visit(node)
            finally:
                self._func_locals_stack.pop()
        return super()._def_visit(node)

    def _eval_identifier(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            return val if val.isidentifier() and not keyword.iskeyword(val) else None
        res = self.eval(node)
        if res is not None and not is_symbolic_ref(res):
            val = self.unwrap(res)
            if (
                isinstance(val, str)
                and val.isidentifier()
                and not keyword.iskeyword(val)
            ):
                return val
        return None

    def _is_globals_items_call(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "items"
            and not node.args
            and not node.keywords
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and self.ctx.remap_is(node.func.value.func.id, ["globals"])
            and self.ctx.is_usable(node.func.value.func.id)
            and not node.func.value.args
            and not node.func.value.keywords
        )

    def _match_key_cmp(
        self, test: ast.AST, key_var: str
    ) -> tuple[str, str] | None:
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
            return None
        op = test.ops[0]
        if isinstance(op, ast.Eq):
            kind = "eq"
        elif isinstance(op, ast.NotEq):
            kind = "neq"
        else:
            return None

        left, right = test.left, test.comparators[0]
        if isinstance(left, ast.Name) and left.id == key_var:
            ident = self._eval_identifier(right)
            return (kind, ident) if ident is not None else None
        if isinstance(right, ast.Name) and right.id == key_var:
            ident = self._eval_identifier(left)
            return (kind, ident) if ident is not None else None
        return None

    def _match_val_call(self, expr: ast.AST, val_var: str) -> ast.Call | None:
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Name)
            and expr.func.id == val_var
        ):
            for arg in expr.args:
                if any(
                    isinstance(n, ast.Name) and n.id == val_var for n in ast.walk(arg)
                ):
                    return None
            for kw in expr.keywords:
                if any(
                    isinstance(n, ast.Name) and n.id == val_var
                    for n in ast.walk(kw.value)
                ):
                    return None
            return expr
        return None

    def visit_Expr(self, node: ast.Expr) -> Any:
        self.generic_visit(node)
        if not isinstance(node.value, ast.ListComp):
            return node

        lc = node.value
        if len(lc.generators) != 1:
            return node
        gen = lc.generators[0]
        if gen.is_async or not self._is_globals_items_call(gen.iter):
            return node
        if not isinstance(gen.target, (ast.Tuple, ast.List)) or len(gen.target.elts) != 2:
            return node
        k_node, v_node = gen.target.elts
        if not isinstance(k_node, ast.Name) or not isinstance(v_node, ast.Name):
            return node
        k_var, v_var = k_node.id, v_node.id
        if k_var == v_var:
            return node

        fn_name: str | None = None
        call_node: ast.Call | None = None

        if not gen.ifs and isinstance(lc.elt, ast.IfExp):
            cmp_res = self._match_key_cmp(lc.elt.test, k_var)
            if cmp_res is not None:
                kind, ident = cmp_res
                if kind == "eq" and _is_pure_fallback(lc.elt.orelse):
                    call_node = self._match_val_call(lc.elt.body, v_var)
                    fn_name = ident
                elif kind == "neq" and _is_pure_fallback(lc.elt.body):
                    call_node = self._match_val_call(lc.elt.orelse, v_var)
                    fn_name = ident
        elif len(gen.ifs) == 1:
            cmp_res = self._match_key_cmp(gen.ifs[0], k_var)
            if cmp_res is not None and cmp_res[0] == "eq":
                call_node = self._match_val_call(lc.elt, v_var)
                fn_name = cmp_res[1]

        if fn_name is None or call_node is None:
            return node

        if fn_name not in self._module_bindings:
            return node

        if any(fn_name in locals_set for locals_set in self._func_locals_stack):
            return node

        LOGGER.debug(f"Simplified globals().items() dispatch -> {fn_name}(...)")
        new_call = ast.Call(
            func=ast.Name(id=fn_name, ctx=ast.Load()),
            args=call_node.args,
            keywords=call_node.keywords,
        )
        return ast.copy_location(ast.Expr(value=new_call), node)
