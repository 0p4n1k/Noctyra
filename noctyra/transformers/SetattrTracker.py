from __future__ import annotations

import ast
import copy
import keyword
from typing import Any

from noctyra.core import ImportSymbol, is_symbolic_ref
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _is_substitutable_value(node: ast.AST) -> bool:
    if isinstance(node, (ast.Constant, ast.Name, ast.Lambda)):
        return True
    if isinstance(node, ast.Attribute):
        return _is_substitutable_value(node.value)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not any(isinstance(e, ast.Starred) for e in node.elts) and all(
            _is_substitutable_value(e) for e in node.elts
        )
    if isinstance(node, ast.Dict):
        return all(
            k is not None
            and _is_substitutable_value(k)
            and _is_substitutable_value(v)
            for k, v in zip(node.keys, node.values)
        )
    return False


def _collect_free_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Lambda):
        params: set[str] = {
            a.arg
            for a in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
        }
        if node.args.vararg is not None:
            params.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            params.add(node.args.kwarg.arg)
        return _collect_free_names(node.body) - params
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


class SetattrTracker(BaseTransformer):
    """Track setattr() mutations on __builtins__, modules, and objects."""

    def __init__(self) -> None:
        super().__init__()
        self._attrs: dict[tuple[str, ...], tuple[ast.expr, set[str]]] = {}
        self._func_locals_stack: list[set[str]] = []
        self._lambda_params_stack: list[set[str]] = []
        self._tracked_stmts: dict[int, tuple[tuple[str, ...], str | None]] = {}
        self._conditional_depth: int = 0
        self._module_aliases: dict[str, set[str]] = {}

    def _is_builtins_namespace(self, name: str) -> bool:
        if name not in ("builtins", "__builtins__"):
            return False
        if not self.ctx.is_usable(name) or self.ctx.remap_get(name) is not None:
            return False
        entry = self.ctx.get(name)
        if entry is None:
            return True
        val = entry.get()
        return isinstance(val, ImportSymbol) and val.module == "builtins"

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

    def _target_key(self, obj: ast.AST, attr: str) -> tuple[str, ...] | None:
        if not isinstance(obj, ast.Name):
            return None
        if self._is_builtins_namespace(obj.id):
            return ("__builtins__", attr)
        entry = self.ctx.get(obj.id)
        if entry is not None:
            val = entry.get()
            if isinstance(val, ImportSymbol):
                self._module_aliases.setdefault(val.module, {val.module}).add(obj.id)
                return ("module", val.module, attr)
        return ("var", obj.id, attr)

    def _invalidate_name(self, name: str) -> None:
        to_del: list[tuple[str, ...]] = []
        for key, (_, free_names) in self._attrs.items():
            if (key[0] == "var" and key[1] == name) or name in free_names:
                to_del.append(key)
        for key in to_del:
            self._attrs.pop(key, None)

    def _invalidate_target(self, obj: ast.AST, attr: str | None = None) -> None:
        if not isinstance(obj, ast.Name):
            return
        if attr is not None:
            key = self._target_key(obj, attr)
            if key is not None:
                self._attrs.pop(key, None)
            return
        prefix: tuple[str, ...]
        if self._is_builtins_namespace(obj.id):
            prefix = ("__builtins__",)
        else:
            entry = self.ctx.get(obj.id)
            if entry is not None and isinstance(entry.get(), ImportSymbol):
                prefix = ("module", entry.get().module)
            else:
                prefix = ("var", obj.id)
        for key in [k for k in self._attrs if k[: len(prefix)] == prefix]:
            self._attrs.pop(key, None)

    def _snapshot(self) -> dict[tuple[str, ...], tuple[ast.expr, set[str]]]:
        return {
            k: (copy.deepcopy(v[0]), set(v[1])) for k, v in self._attrs.items()
        }

    def _merge_branch_changes(
        self,
        before: dict[tuple[str, ...], tuple[ast.expr, set[str]]],
        branch_states: list[dict[tuple[str, ...], tuple[ast.expr, set[str]]]],
    ) -> None:
        merged = {
            k: (copy.deepcopy(v[0]), set(v[1])) for k, v in before.items()
        }
        for state in branch_states:
            all_keys = set(before.keys()) | set(state.keys())
            for k in all_keys:
                if k not in before or k not in state:
                    merged.pop(k, None)
                elif ast.dump(before[k][0]) != ast.dump(state[k][0]):
                    merged.pop(k, None)
        self._attrs = merged

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self._attrs = {}
        self._func_locals_stack = []
        self._lambda_params_stack = []
        self._tracked_stmts = {}
        self._conditional_depth = 0
        self._module_aliases = {}
        result = self.generic_visit(node)
        if isinstance(result, ast.Module) and self._tracked_stmts:
            self._prune_dead_setattr_stmts(result)
        ast.fix_missing_locations(result)
        return result  # type: ignore[return-value]

    def visit_Import(self, node: ast.Import) -> Any:
        super().visit_Import(node)
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._module_aliases.setdefault(alias.name, {alias.name}).add(bound)
        return node

    def visit_Expr(self, node: ast.Expr) -> Any:
        if (
            self._conditional_depth == 0
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and self.ctx.remap_is(node.value.func.id, ["setattr"])
            and self.ctx.is_usable(node.value.func.id)
            and len(node.value.args) == 3
            and not node.value.keywords
            and not any(isinstance(a, ast.Starred) for a in node.value.args)
        ):
            self.generic_visit(node)
            call = node.value
            if isinstance(call, ast.Call) and len(call.args) == 3:
                attr_name = self._eval_identifier(call.args[1])
                if attr_name is not None and _is_substitutable_value(call.args[2]):
                    tkey = self._target_key(call.args[0], attr_name)
                    if tkey is not None:
                        obj_name = (
                            call.args[0].id
                            if isinstance(call.args[0], ast.Name)
                            else None
                        )
                        self._tracked_stmts[id(node)] = (tkey, obj_name)
            return node
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name) or node.keywords:
            return node

        # setattr(obj, 'attr', val)
        if (
            self.ctx.remap_is(node.func.id, ["setattr"])
            and self.ctx.is_usable(node.func.id)
            and len(node.args) == 3
            and not any(isinstance(a, ast.Starred) for a in node.args)
        ):
            attr_name = self._eval_identifier(node.args[1])
            if attr_name is not None:
                tkey = self._target_key(node.args[0], attr_name)
                if tkey is not None:
                    if _is_substitutable_value(node.args[2]):
                        self._attrs[tkey] = (
                            copy.deepcopy(node.args[2]),
                            _collect_free_names(node.args[2]),
                        )
                    else:
                        self._attrs.pop(tkey, None)
            else:
                self._invalidate_target(node.args[0], None)
            return node

        # delattr(obj, 'attr')
        if (
            self.ctx.remap_is(node.func.id, ["delattr"])
            and self.ctx.is_usable(node.func.id)
            and len(node.args) == 2
            and not any(isinstance(a, ast.Starred) for a in node.args)
        ):
            attr_name = self._eval_identifier(node.args[1])
            self._invalidate_target(node.args[0], attr_name)
            return node

        # getattr(obj, 'attr') when tracked
        if (
            self.ctx.remap_is(node.func.id, ["getattr"])
            and self.ctx.is_usable(node.func.id)
            and len(node.args) == 2
            and not any(isinstance(a, ast.Starred) for a in node.args)
        ):
            attr_name = self._eval_identifier(node.args[1])
            if attr_name is not None:
                tkey = self._target_key(node.args[0], attr_name)
                if tkey is not None and tkey in self._attrs:
                    val_node, free_names = self._attrs[tkey]
                    target_name = (
                        node.args[0].id
                        if isinstance(node.args[0], ast.Name)
                        else None
                    )
                    if self._can_substitute(free_names, target_name):
                        LOGGER.debug(f"Resolved tracked getattr -> {tkey}")
                        return ast.copy_location(copy.deepcopy(val_node), node)

        return node

    def _is_shadowed_by_lambda(self, name: str) -> bool:
        return any(name in lp for lp in self._lambda_params_stack)

    def _can_substitute(
        self, val_free_names: set[str], target_name: str | None = None
    ) -> bool:
        if target_name is not None and self._is_shadowed_by_lambda(target_name):
            return False
        if any(
            fn in lp
            for lp in self._lambda_params_stack
            for fn in val_free_names
        ):
            return False
        return True

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        node.args.defaults = [self.visit(d) for d in node.args.defaults]
        node.args.kw_defaults = [
            self.visit(d) if d is not None else None for d in node.args.kw_defaults
        ]
        params: set[str] = {
            a.arg
            for a in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
        }
        if node.args.vararg is not None:
            params.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            params.add(node.args.kwarg.arg)

        saved_attrs = self._snapshot()
        self._lambda_params_stack.append(params)
        self._conditional_depth += 1
        try:
            node.body = self.visit(node.body)
        finally:
            self._conditional_depth -= 1
            self._lambda_params_stack.pop()
            self._attrs = saved_attrs
        return node

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        node.value = self.visit(node.value)
        if isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name):
            tkey = self._target_key(node.value, node.attr)
            if tkey is not None and tkey in self._attrs:
                val_node, free_names = self._attrs[tkey]
                if self._can_substitute(free_names, node.value.id):
                    LOGGER.debug(
                        f"Resolved tracked attribute {node.value.id}.{node.attr}"
                    )
                    return ast.copy_location(copy.deepcopy(val_node), node)
        return node

    def visit_Name(self, node: ast.Name) -> Any:
        if isinstance(node.ctx, ast.Load):
            if (
                not any(node.id in loc for loc in self._func_locals_stack)
                and not self._is_shadowed_by_lambda(node.id)
                and self._is_builtin_usable(node.id)
            ):
                tkey = ("__builtins__", node.id)
                if tkey in self._attrs:
                    val_node, free_names = self._attrs[tkey]
                    if self._can_substitute(free_names, node.id):
                        LOGGER.debug(f"Resolved tracked builtin {node.id}")
                        return ast.copy_location(copy.deepcopy(val_node), node)
        return node

    def visit_Assign(self, node: ast.Assign) -> Any:
        res = super().visit_Assign(node)
        for target in node.targets:
            for name in self._collect_target_names(target):
                self._invalidate_name(name)
        return res

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        res = super().visit_AugAssign(node)
        for name in self._collect_target_names(node.target):
            self._invalidate_name(name)
        return res

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        res = super().visit_AnnAssign(node)
        for name in self._collect_target_names(node.target):
            self._invalidate_name(name)
        return res

    def visit_Delete(self, node: ast.Delete) -> Any:
        res = super().visit_Delete(node)
        for target in node.targets:
            for name in self._collect_target_names(target):
                self._invalidate_name(name)
        return res

    def visit_NamedExpr(self, node: ast.NamedExpr) -> Any:
        res = super().visit_NamedExpr(node)
        self._invalidate_name(node.target.id)
        return res

    def visit_If(self, node: ast.If) -> Any:
        node.test = self.visit(node.test)
        before = self._snapshot()
        old_ctx = self.ctx
        assigned = self._collect_assigned_names(node.body) | self._collect_assigned_names(
            node.orelse
        )

        self._conditional_depth += 1
        body_ctx = self.ctx.__class__(parent=old_ctx)
        self.ctx = body_ctx
        self._attrs = self._snapshot()
        node.body = self._visit_stmt_list(node.body)
        body_attrs = self._attrs

        else_ctx = self.ctx.__class__(parent=old_ctx)
        self.ctx = else_ctx
        self._attrs = self._snapshot()
        self._attrs = {k: (copy.deepcopy(v[0]), set(v[1])) for k, v in before.items()}
        node.orelse = self._visit_stmt_list(node.orelse)
        else_attrs = self._attrs
        self._conditional_depth -= 1

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)
            self._invalidate_name(name)

        self._merge_branch_changes(before, [body_attrs, else_attrs])
        return node

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> Any:
        before = self._snapshot()
        self._conditional_depth += 1
        res = super()._visit_loop(node)
        self._conditional_depth -= 1
        after = self._attrs
        self._merge_branch_changes(before, [after])
        return res

    def visit_Try(self, node: ast.Try | Any) -> Any:
        before = self._snapshot()
        self._conditional_depth += 1
        res = super().visit_Try(node)
        self._conditional_depth -= 1
        after = self._attrs
        self._merge_branch_changes(before, [after])
        return res

    def _def_visit(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Any:
        saved_attrs = self._snapshot()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_locals = self._collect_func_locals(node)
            for name in func_locals:
                self._invalidate_name(name)
            self._func_locals_stack.append(func_locals)
            self._conditional_depth += 1
            try:
                res = super()._def_visit(node)
            finally:
                self._conditional_depth -= 1
                self._func_locals_stack.pop()
                self._attrs = saved_attrs
            self._invalidate_name(node.name)
            return res

        self._conditional_depth += 1
        try:
            res = super()._def_visit(node)
        finally:
            self._conditional_depth -= 1
            self._attrs = saved_attrs
        self._invalidate_name(node.name)
        return res

    def _prune_dead_setattr_stmts(self, module: ast.Module) -> None:
        tracked_ids = set(self._tracked_stmts.keys())
        remaining_load_names: set[str] = set()
        remaining_attrs: set[tuple[str, str]] = set()
        escaped_vars: set[str] = set()
        dynamic_reflection_targets: set[str] = set()

        def _scan(node: ast.AST) -> None:
            if id(node) in tracked_ids:
                return
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                remaining_load_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    remaining_attrs.add((node.value.id, node.attr))
                    if node.attr == "__dict__":
                        dynamic_reflection_targets.add(node.value.id)
            elif isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id in ("getattr", "hasattr")
                    and len(node.args) >= 2
                ):
                    if isinstance(node.args[0], ast.Name):
                        if (
                            isinstance(node.args[1], ast.Constant)
                            and isinstance(node.args[1].value, str)
                        ):
                            remaining_attrs.add(
                                (node.args[0].id, node.args[1].value)
                            )
                        else:
                            dynamic_reflection_targets.add(node.args[0].id)
                    for arg in node.args[2:]:
                        val = arg.value if isinstance(arg, ast.Starred) else arg
                        if isinstance(val, ast.Name):
                            escaped_vars.add(val.id)
                    for kw in node.keywords:
                        if isinstance(kw.value, ast.Name):
                            escaped_vars.add(kw.value.id)
                elif (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "vars"
                    and len(node.args) == 1
                ):
                    if isinstance(node.args[0], ast.Name):
                        dynamic_reflection_targets.add(node.args[0].id)
                    for kw in node.keywords:
                        if isinstance(kw.value, ast.Name):
                            escaped_vars.add(kw.value.id)
                else:
                    for arg in node.args:
                        val = arg.value if isinstance(arg, ast.Starred) else arg
                        if isinstance(val, ast.Name):
                            escaped_vars.add(val.id)
                    for kw in node.keywords:
                        if isinstance(kw.value, ast.Name):
                            escaped_vars.add(kw.value.id)
            elif isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)):
                if node.value is not None and isinstance(node.value, ast.Name):
                    escaped_vars.add(node.value.id)
            elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                for elt in node.elts:
                    val = elt.value if isinstance(elt, ast.Starred) else elt
                    if isinstance(val, ast.Name):
                        escaped_vars.add(val.id)
            elif isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Name):
                        escaped_vars.add(k.id)
                for v in node.values:
                    if isinstance(v, ast.Name):
                        escaped_vars.add(v.id)
            elif isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Name):
                    escaped_vars.add(node.value.id)
            elif isinstance(node, ast.AnnAssign):
                if node.value is not None and isinstance(node.value, ast.Name):
                    escaped_vars.add(node.value.id)
            elif isinstance(node, ast.NamedExpr):
                if isinstance(node.value, ast.Name):
                    escaped_vars.add(node.value.id)
            for child in ast.iter_child_nodes(node):
                _scan(child)

        _scan(module)

        def _is_safe_to_remove(stmt_id: int) -> bool:
            tkey, obj_name = self._tracked_stmts[stmt_id]
            kind = tkey[0]
            if kind == "__builtins__":
                attr = tkey[1]
                if attr in remaining_load_names:
                    return False
                if ("builtins", attr) in remaining_attrs or (
                    "__builtins__",
                    attr,
                ) in remaining_attrs:
                    return False
                if (
                    "builtins" in dynamic_reflection_targets
                    or "__builtins__" in dynamic_reflection_targets
                ):
                    return False
                return True

            if kind == "module":
                mod_name, attr = tkey[1], tkey[2]
                aliases = set(self._module_aliases.get(mod_name, {mod_name}))
                if obj_name:
                    aliases.add(obj_name)
                for alias in aliases:
                    if (alias, attr) in remaining_attrs:
                        return False
                    if (
                        alias in dynamic_reflection_targets
                        or alias in escaped_vars
                    ):
                        return False
                return True

            if kind == "var":
                var_name, attr = tkey[1], tkey[2]
                if (var_name, attr) in remaining_attrs:
                    return False
                if var_name in dynamic_reflection_targets or var_name in escaped_vars:
                    return False
                return True

            return False

        to_remove = {sid for sid in tracked_ids if _is_safe_to_remove(sid)}
        if not to_remove:
            return

        class _StmtRemover(ast.NodeTransformer):
            def _filter(self, stmts: list[ast.stmt], ensure_non_empty: bool, ref: ast.AST) -> list[ast.stmt]:
                out = [s for s in stmts if id(s) not in to_remove]
                if ensure_non_empty and not out:
                    return [ast.copy_location(ast.Pass(), ref)]
                return out

            def visit_Module(self, m: ast.Module) -> ast.Module:
                self.generic_visit(m)
                m.body = self._filter(m.body, False, m)
                return m

        _StmtRemover().visit(module)
