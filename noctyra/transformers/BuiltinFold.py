import ast
import copy
from typing import Any

from noctyra.core import Context
from noctyra.core.Transformer import UNRESOLVED, BaseTransformer
from noctyra.utils import IMMUTABLE_TYPES, LOGGER
from noctyra.utils.Shared import is_pure_expr


def _is_hoist_safe_elem(node: ast.AST) -> bool:
    if isinstance(node, (ast.Constant, ast.Lambda)):
        return True
    if isinstance(node, ast.Tuple):
        return all(
            not isinstance(elt, ast.Starred) and _is_hoist_safe_elem(elt)
            for elt in node.elts
        )
    return False


class BuiltinFolder(BaseTransformer):
    """Fold pure builtin calls into AST constants, lists, or dicts."""

    def __init__(self) -> None:
        super().__init__()
        self._hoist_stack: list[list[ast.stmt] | None] = []
        self._discard_target: ast.AST | None = None

    def _visit_stmt_with_hoist(self, node: ast.stmt, visit_fn: Any) -> Any:
        self._hoist_stack.append([])
        try:
            res = visit_fn(node)
        finally:
            hoisted = self._hoist_stack.pop()
        if hoisted:
            if isinstance(res, list):
                return [*hoisted, *res]
            return [*hoisted, res]
        return res

    def visit_Expr(self, node: ast.Expr) -> Any:
        self._hoist_stack.append([])
        old_discard = self._discard_target
        self._discard_target = node.value
        try:
            node.value = self.visit(node.value)
        finally:
            self._discard_target = old_discard
            hoisted = self._hoist_stack.pop()
        if hoisted:
            return [*hoisted, node]
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        self._hoist_stack.append([])
        old_discard = self._discard_target
        try:
            node.target = self.visit(node.target)
            self._discard_target = node.annotation
            node.annotation = self.visit(node.annotation)
            self._discard_target = None
            if node.value is not None:
                node.value = self.visit(node.value)
        finally:
            self._discard_target = old_discard
            hoisted = self._hoist_stack.pop()

        for name in self._collect_target_names(node.target):
            self.ctx.invalidate(name)

        if hoisted:
            return [*hoisted, node]
        return node

    def visit_Assign(self, node: ast.Assign) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_Assign)

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_AugAssign)

    def visit_Return(self, node: ast.Return) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Raise(self, node: ast.Raise) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Assert(self, node: ast.Assert) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Delete(self, node: ast.Delete) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_Delete)

    def visit_If(self, node: ast.If) -> Any:
        self._hoist_stack.append([])
        try:
            node.test = self.visit(node.test)
        finally:
            hoisted = self._hoist_stack.pop()

        old_ctx = self.ctx
        assigned = self._collect_assigned_names(
            node.body
        ) | self._collect_assigned_names(node.orelse)

        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self._visit_stmt_list(node.body)

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)

        if hoisted:
            return [*hoisted, node]
        return node

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> Any:
        assigned = self._collect_assigned_names(
            node.body
        ) | self._collect_assigned_names(node.orelse)

        hoisted: list[ast.stmt] | None = None
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._hoist_stack.append([])
            try:
                node.iter = self.visit(node.iter)
            finally:
                hoisted = self._hoist_stack.pop()
            assigned.update(self._collect_target_names(node.target))

        for name in assigned:
            self.ctx.invalidate(name)

        if isinstance(node, ast.While):
            self._hoist_stack.append(None)
            try:
                node.test = self.visit(node.test)
            finally:
                self._hoist_stack.pop()

        old_ctx = self.ctx
        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self._visit_stmt_list(node.body)

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)

        if hoisted:
            return [*hoisted, node]
        return node

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._hoist_stack.append(None)
        try:
            return self.generic_visit(node)
        finally:
            self._hoist_stack.pop()

    def _visit_comp(self, node: ast.AST) -> ast.AST:
        self._hoist_stack.append(None)
        try:
            return super()._visit_comp(node)
        finally:
            self._hoist_stack.pop()

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        node.test = self.visit(node.test)

        old_ctx = self.ctx
        walrus_targets: set[str] = set()
        for branch in (node.body, node.orelse):
            if isinstance(branch, ast.NamedExpr):
                walrus_targets.add(branch.target.id)
            self._collect_nested_walrus(branch, walrus_targets)

        self._hoist_stack.append(None)
        try:
            body_ctx = Context(parent=old_ctx)
            self.ctx = body_ctx
            node.body = self.visit(node.body)

            else_ctx = Context(parent=old_ctx)
            self.ctx = else_ctx
            node.orelse = self.visit(node.orelse)
        finally:
            self.ctx = old_ctx
            self._hoist_stack.pop()

        for name in walrus_targets | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if not node.values:
            return node
        node.values[0] = self.visit(node.values[0])
        if len(node.values) > 1:
            old_ctx = self.ctx
            walrus_targets: set[str] = set()
            for val in node.values[1:]:
                if isinstance(val, ast.NamedExpr):
                    walrus_targets.add(val.target.id)
                self._collect_nested_walrus(val, walrus_targets)

            sub_ctx = Context(parent=old_ctx)
            self.ctx = sub_ctx
            self._hoist_stack.append(None)
            try:
                node.values[1:] = [self.visit(val) for val in node.values[1:]]
            finally:
                self.ctx = old_ctx
                self._hoist_stack.pop()

            for name in walrus_targets | set(sub_ctx.invalidated):
                self.ctx.invalidate(name)
        return node

    def _unwrap_single_element_key_call(
        self, node: ast.Call, func_name: str, is_discarded: bool
    ) -> ast.AST | None:
        if len(node.args) != 1 or isinstance(node.args[0], ast.Starred):
            return None

        arg = node.args[0]
        if (
            not isinstance(arg, (ast.List, ast.Tuple))
            or len(arg.elts) != 1
            or isinstance(arg.elts[0], ast.Starred)
        ):
            return None

        allowed_kws = {"key", "reverse"} if func_name == "sorted" else {"key"}
        kw_map: dict[str, ast.keyword] = {}
        for kw in node.keywords:
            if kw.arg is None or kw.arg not in allowed_kws or kw.arg in kw_map:
                return None
            kw_map[kw.arg] = kw

        if "reverse" in kw_map and not is_pure_expr(
            kw_map["reverse"].value, allow_containers=True
        ):
            return None

        x = arg.elts[0]
        key_kw = kw_map.get("key")
        if key_kw is None or (
            isinstance(key_kw.value, ast.Constant) and key_kw.value.value is None
        ):
            LOGGER.debug(f"Simplified single-element {func_name}(..., key=None)")
            if func_name == "sorted":
                return ast.copy_location(ast.List(elts=[x], ctx=ast.Load()), node)
            return x

        fn = key_kw.value
        key_call = ast.copy_location(
            ast.Call(func=fn, args=[x], keywords=[]), node
        )

        if is_discarded:
            LOGGER.debug(
                f"Unwrapped discarded single-element {func_name}(..., key=fn) to fn(x)"
            )
            return key_call

        if (
            self._hoist_stack
            and self._hoist_stack[-1] is not None
            and _is_hoist_safe_elem(x)
        ):
            hoist_expr = ast.copy_location(ast.Expr(value=key_call), node)
            ast.fix_missing_locations(hoist_expr)
            self._hoist_stack[-1].append(hoist_expr)
            LOGGER.debug(
                f"Hoisted key call from single-element {func_name}(..., key=fn)"
            )
            if func_name == "sorted":
                return ast.copy_location(
                    ast.List(elts=[copy.deepcopy(x)], ctx=ast.Load()), node
                )
            return copy.deepcopy(x)

        return None

    def visit_Call(self, node: ast.Call) -> ast.AST:
        is_discarded = self._discard_target is node
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name):
            return node

        func_name = node.func.id
        if not self._is_builtin_usable(func_name):
            return node

        if func_name in ("sorted", "min", "max") and node.keywords:
            unwrapped = self._unwrap_single_element_key_call(
                node, func_name, is_discarded
            )
            if unwrapped is not None:
                return unwrapped
            return node

        if node.keywords:
            return node

        if func_name == "int" and len(node.args) == 2:
            s = self._eval_const_expr(node.args[0])
            base = self._eval_const_expr(node.args[1])
            if (
                isinstance(s, (str, bytes))
                and isinstance(base, int)
                and not isinstance(base, bool)
            ):
                try:
                    int_res = int(s, base)
                except (ValueError, TypeError, OverflowError):
                    return node
                if abs(int_res) <= self.max_allocation:
                    LOGGER.debug(
                        f"Folded int({s!r}, {base!r}) into constant: {int_res!r}"
                    )
                    return ast.copy_location(ast.Constant(value=int_res), node)
            return node

        if func_name in ("bin", "oct", "ascii", "repr") and len(node.args) == 1:
            val = self._eval_const_expr(node.args[0])
            if val is UNRESOLVED or not isinstance(val, IMMUTABLE_TYPES):
                return node
            try:
                if func_name in ("bin", "oct"):
                    if not isinstance(val, int):
                        return node
                    if val.bit_length() > self.max_allocation:
                        return node
                    str_res = bin(val) if func_name == "bin" else oct(val)
                elif func_name == "ascii":
                    str_res = ascii(val)
                else:
                    str_res = repr(val)
            except (TypeError, ValueError, OverflowError):
                return node
            if len(str_res) <= self.max_allocation:
                LOGGER.debug(f"Folded {func_name}(...) into constant: {str_res!r}")
                return ast.copy_location(ast.Constant(value=str_res), node)
            return node

        if func_name in ("any", "all") and len(node.args) == 1:
            it = self._eval_const_expr(node.args[0])
            if (
                isinstance(it, (list, tuple, set, str, bytes, dict))
                and len(it) <= self.max_allocation
            ):
                bool_res = bool(any(it) if func_name == "any" else all(it))
                LOGGER.debug(f"Folded {func_name}(...) into constant: {bool_res!r}")
                return ast.copy_location(ast.Constant(value=bool_res), node)
            return node

        if func_name == "sorted" and len(node.args) == 1:
            it = self._eval_const_expr(node.args[0])
            if (
                isinstance(it, (list, tuple, set, str, bytes, dict))
                and len(it) <= self.max_allocation
                and all(isinstance(el, IMMUTABLE_TYPES) for el in it)
            ):
                try:
                    sorted_items = sorted(it)
                except TypeError:
                    return node
                elts: list[ast.expr] = [
                    ast.copy_location(ast.Constant(value=v), node) for v in sorted_items
                ]
                LOGGER.debug(f"Folded sorted(...) into list of {len(elts)} constants")
                return ast.copy_location(ast.List(elts=elts, ctx=ast.Load()), node)
            return node

        if func_name == "dict" and len(node.args) == 1:
            arg = node.args[0]
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "zip"
                and self._is_builtin_usable("zip")
                and not arg.keywords
                and len(arg.args) == 2
            ):
                keys_seq = self._eval_const_expr(arg.args[0])
                vals_seq = self._eval_const_expr(arg.args[1])
                if (
                    isinstance(keys_seq, (list, tuple, str, bytes))
                    and isinstance(vals_seq, (list, tuple, str, bytes))
                    and len(keys_seq) <= self.max_allocation
                    and len(vals_seq) <= self.max_allocation
                    and all(isinstance(k, IMMUTABLE_TYPES) for k in keys_seq)
                    and all(isinstance(v, IMMUTABLE_TYPES) for v in vals_seq)
                ):
                    try:
                        folded_dict = dict(zip(keys_seq, vals_seq))
                    except TypeError:
                        return node
                    keys: list[ast.expr | None] = [
                        ast.copy_location(ast.Constant(value=k), node)
                        for k in folded_dict.keys()
                    ]
                    values: list[ast.expr] = [
                        ast.copy_location(ast.Constant(value=v), node)
                        for v in folded_dict.values()
                    ]
                    LOGGER.debug(
                        f"Folded dict(zip(...)) into dict of {len(keys)} entries"
                    )
                    return ast.copy_location(ast.Dict(keys=keys, values=values), node)
            pairs_seq = self._eval_const_expr(arg)
            if (
                isinstance(pairs_seq, (list, tuple))
                and len(pairs_seq) <= self.max_allocation
                and all(
                    isinstance(p, (list, tuple))
                    and len(p) == 2
                    and isinstance(p[0], IMMUTABLE_TYPES)
                    and isinstance(p[1], IMMUTABLE_TYPES)
                    for p in pairs_seq
                )
            ):
                try:
                    folded_dict = dict(pairs_seq)
                except TypeError:
                    return node
                keys = [
                    ast.copy_location(ast.Constant(value=k), node)
                    for k in folded_dict.keys()
                ]
                values = [
                    ast.copy_location(ast.Constant(value=v), node)
                    for v in folded_dict.values()
                ]
                LOGGER.debug(f"Folded dict(...) into dict of {len(keys)} entries")
                return ast.copy_location(ast.Dict(keys=keys, values=values), node)
            return node

        return node
