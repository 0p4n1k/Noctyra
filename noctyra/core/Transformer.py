from noctyra.core import (
    LambdaType,
    ImportSymbol,
    Context,
    is_symbolic_ref,
    unwrap as core_unwrap,
)
from noctyra.transformers.safe_eval import safe_eval
from typing import Any
import ast

UNRESOLVED = object()

_MUTATING_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "sort",
        "reverse",
        "update",
        "setdefault",
        "add",
        "discard",
    }
)


class BaseTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.ctx: Context = Context()
        self.max_depth: int = 50
        self.max_allocation: int = 100_000

    def visit(self, node: ast.AST) -> Any:
        result = super().visit(node)
        if isinstance(node, ast.Call):
            self._invalidate_call_effects(node)
        return result

    def run(
        self,
        node: ast.AST,
        ctx: Context | None = None,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ) -> ast.AST:

        self.ctx = ctx or Context()
        self.max_depth = max_depth
        self.max_allocation = max_allocation
        return self.visit(node)

    def eval(self, node: ast.AST | None, ctx: Context | None = None):
        return safe_eval(
            node,
            ctx=ctx or self.ctx,
            max_depth=self.max_depth,
            max_allocation=self.max_allocation,
        )

    def unwrap(self, obj: Any) -> Any:
        return core_unwrap(obj)

    def _is_builtin_usable(self, name: str) -> bool:
        return (
            self.ctx.is_usable(name)
            and not self.ctx.has(name)
            and self.ctx.remap_get(name) is None
        )

    def _within_allocation(self, value: Any) -> bool:
        if isinstance(value, (str, bytes, bytearray, list, tuple, dict, set)):
            return len(value) <= self.max_allocation
        return True

    def _eval_const_expr(
        self, node: ast.AST | None, *, eval_subscripts: bool = False
    ) -> Any:
        if node is None:
            return UNRESOLVED

        res = self.eval(node)
        if res is not None and not is_symbolic_ref(res):
            val = self.unwrap(res)
            if self._within_allocation(val):
                return val
            return UNRESOLVED

        if isinstance(node, ast.Dict):
            result: dict[Any, Any] = {}
            for k_node, v_node in zip(node.keys, node.values):
                if k_node is None:
                    spread = self._eval_const_expr(
                        v_node, eval_subscripts=eval_subscripts
                    )
                    if not isinstance(spread, dict):
                        return UNRESOLVED
                    result.update(spread)
                else:
                    key = self._eval_const_expr(
                        k_node, eval_subscripts=eval_subscripts
                    )
                    val = self._eval_const_expr(
                        v_node, eval_subscripts=eval_subscripts
                    )
                    if key is UNRESOLVED or val is UNRESOLVED:
                        return UNRESOLVED
                    try:
                        result[key] = val
                    except TypeError:
                        return UNRESOLVED
                if len(result) > self.max_allocation:
                    return UNRESOLVED
            return result

        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if len(node.elts) > self.max_allocation:
                return UNRESOLVED
            items: list[Any] = []
            for elt in node.elts:
                if isinstance(elt, ast.Starred):
                    return UNRESOLVED
                item = self._eval_const_expr(elt, eval_subscripts=eval_subscripts)
                if item is UNRESOLVED:
                    return UNRESOLVED
                items.append(item)
            if isinstance(node, ast.List):
                return items
            if isinstance(node, ast.Tuple):
                return tuple(items)
            try:
                return set(items)
            except TypeError:
                return UNRESOLVED

        if eval_subscripts and isinstance(node, ast.Slice):
            lower = (
                self._eval_const_expr(node.lower, eval_subscripts=True)
                if node.lower is not None
                else None
            )
            upper = (
                self._eval_const_expr(node.upper, eval_subscripts=True)
                if node.upper is not None
                else None
            )
            step = (
                self._eval_const_expr(node.step, eval_subscripts=True)
                if node.step is not None
                else None
            )
            if lower is UNRESOLVED or upper is UNRESOLVED or step is UNRESOLVED:
                return UNRESOLVED
            return slice(lower, upper, step)

        if eval_subscripts and isinstance(node, ast.Subscript):
            target = self._eval_const_expr(node.value, eval_subscripts=True)
            key = self._eval_const_expr(node.slice, eval_subscripts=True)
            if target is UNRESOLVED or key is UNRESOLVED:
                return UNRESOLVED
            try:
                val = target[key]
            except Exception:
                return UNRESOLVED
            if self._within_allocation(val):
                return val
            return UNRESOLVED

        return UNRESOLVED

    def _collect_target_names(self, target: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                names.update(self._collect_target_names(elt))
        elif isinstance(target, ast.Starred):
            names.update(self._collect_target_names(target.value))
        elif isinstance(target, (ast.Subscript, ast.Attribute)):
            base: ast.AST = target.value
            while isinstance(base, (ast.Subscript, ast.Attribute)):
                base = base.value
            if isinstance(base, ast.Name):
                names.add(base.id)
        return names

    def _collect_assigned_names(self, stmts: list[ast.stmt]) -> set[str]:
        assigned: set[str] = set()
        for stmt in stmts:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Assign):
                    for t in child.targets:
                        assigned.update(self._collect_target_names(t))
                elif isinstance(child, ast.AugAssign):
                    assigned.update(self._collect_target_names(child.target))
                elif isinstance(child, ast.AnnAssign):
                    assigned.update(self._collect_target_names(child.target))
                elif isinstance(child, (ast.For, ast.AsyncFor)):
                    assigned.update(self._collect_target_names(child.target))
                elif isinstance(child, (ast.With, ast.AsyncWith)):
                    for item in child.items:
                        if item.optional_vars is not None:
                            assigned.update(
                                self._collect_target_names(item.optional_vars)
                            )
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    assigned.add(child.name)
                elif isinstance(child, ast.NamedExpr):
                    assigned.add(child.target.id)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    assigned.add(child.name)
                elif isinstance(child, ast.Delete):
                    for t in child.targets:
                        assigned.update(self._collect_target_names(t))
        return assigned

    def _collect_func_locals(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> set[str]:
        locals_set: set[str] = set()
        globals_or_nonlocals: set[str] = set()
        for arg in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        ):
            locals_set.add(arg.arg)
        if node.args.vararg is not None:
            locals_set.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            locals_set.add(node.args.kwarg.arg)

        def _walk_scope(stmts: list[ast.stmt]) -> None:
            for stmt in stmts:
                if isinstance(stmt, (ast.Global, ast.Nonlocal)):
                    globals_or_nonlocals.update(stmt.names)
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    locals_set.add(stmt.name)
                else:
                    if isinstance(stmt, ast.Assign):
                        for t in stmt.targets:
                            locals_set.update(self._collect_target_names(t))
                    elif isinstance(stmt, ast.AugAssign):
                        locals_set.update(self._collect_target_names(stmt.target))
                    elif isinstance(stmt, ast.AnnAssign):
                        locals_set.update(self._collect_target_names(stmt.target))
                    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                        locals_set.update(self._collect_target_names(stmt.target))
                    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                        for item in stmt.items:
                            if item.optional_vars is not None:
                                locals_set.update(
                                    self._collect_target_names(item.optional_vars)
                                )
                    elif isinstance(stmt, ast.Import):
                        for alias in stmt.names:
                            locals_set.add(alias.asname or alias.name.split(".")[0])
                    elif isinstance(stmt, ast.Delete):
                        for t in stmt.targets:
                            locals_set.update(self._collect_target_names(t))
                    elif isinstance(stmt, ast.ImportFrom):
                        for alias in stmt.names:
                            if alias.name != "*":
                                locals_set.add(alias.asname or alias.name)
                    self._collect_nested_walrus(stmt, locals_set)
                    for field_name in ("body", "orelse", "finalbody"):
                        sub = getattr(stmt, field_name, None)
                        if isinstance(sub, list):
                            _walk_scope(sub)
                    if isinstance(stmt, ast.Try):
                        for handler in stmt.handlers:
                            if handler.name:
                                locals_set.add(handler.name)
                            _walk_scope(handler.body)

        _walk_scope(node.body)
        return locals_set - globals_or_nonlocals

    @staticmethod
    def _collect_nested_walrus(node: ast.AST, locals_set: set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.NamedExpr):
                locals_set.add(child.target.id)
            BaseTransformer._collect_nested_walrus(child, locals_set)

    def _def_visit(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        old_ctx = self.ctx

        self.ctx = Context(parent=old_ctx)
        self.ctx.invalidate(node.name)

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for local_name in self._collect_func_locals(node):
                self.ctx.invalidate(local_name)

        result = self.generic_visit(node)

        self.ctx = old_ctx
        self.ctx.invalidate(node.name)
        return result

    def visit_Import(self, node: ast.Import) -> Any:
        for name in node.names:
            self.ctx.set(name.asname or name.name, ImportSymbol(name.name))

        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        if node.module:
            for alias in node.names:
                if alias.name != "*":
                    self.ctx.set(
                        alias.asname or alias.name,
                        ImportSymbol(f"{node.module}.{alias.name}"),
                    )
        return node

    def _visit_comp(self, node: ast.AST) -> ast.AST:
        if not isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            return self.generic_visit(node)

        old_ctx = self.ctx
        if node.generators:
            node.generators[0].iter = self.visit(node.generators[0].iter)

        comp_ctx = Context(parent=old_ctx)
        walrus_targets: set[str] = set()
        for i, comp in enumerate(node.generators):
            if i > 0:
                if isinstance(comp.iter, ast.NamedExpr):
                    walrus_targets.add(comp.iter.target.id)
                self._collect_nested_walrus(comp.iter, walrus_targets)
            for cond in comp.ifs:
                if isinstance(cond, ast.NamedExpr):
                    walrus_targets.add(cond.target.id)
                self._collect_nested_walrus(cond, walrus_targets)
        if isinstance(node, ast.DictComp):
            for sub in (node.key, node.value):
                if sub is not None:
                    if isinstance(sub, ast.NamedExpr):
                        walrus_targets.add(sub.target.id)
                    self._collect_nested_walrus(sub, walrus_targets)
        else:
            if isinstance(node.elt, ast.NamedExpr):
                walrus_targets.add(node.elt.target.id)
            self._collect_nested_walrus(node.elt, walrus_targets)

        for name in walrus_targets:
            comp_ctx.invalidate(name)

        self.ctx = comp_ctx
        for i, comp in enumerate(node.generators):
            if i > 0:
                comp.iter = self.visit(comp.iter)
            for name in self._collect_target_names(comp.target):
                self.ctx.invalidate(name)
            comp.ifs = [self.visit(cond) for cond in comp.ifs]

        if isinstance(node, ast.DictComp):
            node.key = self.visit(node.key)
            if node.value is not None:
                node.value = self.visit(node.value)
        else:
            node.elt = self.visit(node.elt)

        self.ctx = old_ctx
        for name in walrus_targets | set(comp_ctx.invalidated):
            self.ctx.invalidate(name)
        return node

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        old_ctx = self.ctx
        node.args.defaults = [self.visit(d) for d in node.args.defaults]
        node.args.kw_defaults = [
            self.visit(d) if d is not None else None for d in node.args.kw_defaults
        ]

        lambda_ctx = Context(parent=old_ctx)
        for arg in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        ):
            lambda_ctx.invalidate(arg.arg)
        if node.args.vararg is not None:
            lambda_ctx.invalidate(node.args.vararg.arg)
        if node.args.kwarg is not None:
            lambda_ctx.invalidate(node.args.kwarg.arg)

        self.ctx = lambda_ctx
        node.body = self.visit(node.body)
        self.ctx = old_ctx
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        return self._visit_comp(node)

    def visit_SetComp(self, node: ast.SetComp) -> ast.AST:
        return self._visit_comp(node)

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        return self._visit_comp(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.AST:
        return self._visit_comp(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        self.generic_visit(node)
        for name in self._collect_target_names(node.target):
            self.ctx.invalidate(name)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        self.generic_visit(node)
        for name in self._collect_target_names(node.target):
            self.ctx.invalidate(name)
        return node

    _READONLY_BUILTINS = frozenset(
        {
            "len",
            "sum",
            "min",
            "max",
            "sorted",
            "any",
            "all",
            "list",
            "tuple",
            "dict",
            "set",
            "reversed",
            "enumerate",
            "zip",
            "map",
            "repr",
            "ascii",
            "type",
            "isinstance",
            "bool",
            "print",
            "id",
            "hash",
        }
    )

    def _invalidate_mutable_aliases(self) -> None:
        ctx: Context | None = self.ctx
        while ctx is not None:
            for var in list(ctx.vars):
                if isinstance(core_unwrap(var.get()), (list, dict, set, bytearray)):
                    self.ctx.invalidate(var.name)
            ctx = ctx.parent

    def visit_Delete(self, node: ast.Delete) -> Any:
        self.generic_visit(node)
        for t in node.targets:
            for name in self._collect_target_names(t):
                self.ctx.invalidate(name)
            if isinstance(t, ast.Subscript):
                self._invalidate_mutable_aliases()
        return node

    def visit_NamedExpr(self, node: ast.NamedExpr) -> Any:
        node.value = self.visit(node.value)
        kind, payload = self._plan_bind(node.target, node.value)
        self._apply_bind_plan(kind, payload)
        return node

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        node.test = self.visit(node.test)

        old_ctx = self.ctx
        walrus_targets: set[str] = set()
        for branch in (node.body, node.orelse):
            if isinstance(branch, ast.NamedExpr):
                walrus_targets.add(branch.target.id)
            self._collect_nested_walrus(branch, walrus_targets)

        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self.visit(node.body)

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        node.orelse = self.visit(node.orelse)

        self.ctx = old_ctx
        for name in walrus_targets | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if not node.values:
            return node
        is_or = isinstance(node.op, ast.Or)
        idx = 0
        while idx < len(node.values):
            node.values[idx] = self.visit(node.values[idx])
            if idx + 1 >= len(node.values):
                return node
            val_res = self.eval(node.values[idx])
            if val_res is None or is_symbolic_ref(val_res):
                if isinstance(val_res, (ImportSymbol, LambdaType)):
                    continues = not is_or
                else:
                    break
            else:
                truth = bool(self.unwrap(val_res))
                continues = (not truth) if is_or else truth
            if not continues:
                break
            idx += 1

        if idx + 1 < len(node.values):
            old_ctx = self.ctx
            walrus_targets: set[str] = set()
            for val in node.values[idx + 1 :]:
                if isinstance(val, ast.NamedExpr):
                    walrus_targets.add(val.target.id)
                self._collect_nested_walrus(val, walrus_targets)

            sub_ctx = Context(parent=old_ctx)
            self.ctx = sub_ctx
            node.values[idx + 1 :] = [self.visit(val) for val in node.values[idx + 1 :]]

            self.ctx = old_ctx
            for name in walrus_targets | set(sub_ctx.invalidated):
                self.ctx.invalidate(name)
        return node

    def visit_With(self, node: ast.With) -> Any:
        return self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        return self._visit_with(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> Any:
        for item in node.items:
            item.context_expr = self.visit(item.context_expr)
            if item.optional_vars is not None:
                for name in self._collect_target_names(item.optional_vars):
                    self.ctx.invalidate(name)
        node.body = self._visit_stmt_list(node.body)
        return node

    def _invalidate_call_effects(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
        ):
            for name in self._collect_target_names(node.func):
                self.ctx.invalidate(name)
            self._invalidate_mutable_aliases()
            return

        is_readonly_builtin = (
            isinstance(node.func, ast.Name)
            and node.func.id in self._READONLY_BUILTINS
            and self._is_builtin_usable(node.func.id)
        )
        if not is_readonly_builtin:
            args_to_check = [
                a.value if isinstance(a, ast.Starred) else a for a in node.args
            ] + [kw.value for kw in node.keywords]
            for arg in args_to_check:
                if isinstance(arg, ast.Name):
                    var = self.ctx.get(arg.id)
                    if var is not None and isinstance(
                        core_unwrap(var.get()), (list, dict, set, bytearray)
                    ):
                        self.ctx.invalidate(arg.id)
                        self._invalidate_mutable_aliases()

    def visit_Call(self, node: ast.Call) -> Any:
        self.generic_visit(node)
        return node

    def _plan_bind(
        self, target: ast.AST, val_node: ast.AST | None, evaluated: Any = UNRESOLVED
    ) -> tuple[str, Any]:
        """Snapshot what a Name target should bind to before mutating self.ctx."""
        if not isinstance(target, ast.Name):
            return ("invalidate", self._collect_target_names(target))

        if val_node is not None and isinstance(val_node, ast.Lambda):
            return ("set", (target.id, LambdaType(val_node.body, val_node.args)))

        val = (
            evaluated
            if evaluated is not UNRESOLVED
            else (self.eval(val_node) if val_node is not None else None)
        )
        if val is not None:
            return ("set", (target.id, val))
        if val_node is not None and isinstance(val_node, ast.Name):
            return ("remap", (target.id, val_node.id))
        if val_node is not None and isinstance(val_node, ast.Attribute):
            base = self.eval(val_node.value)
            if isinstance(base, ImportSymbol):
                return ("set", (target.id, ImportSymbol(f"{base.module}.{val_node.attr}")))
        return ("invalidate", {target.id})

    def _apply_bind_plan(self, kind: str, payload: Any) -> None:
        if kind == "set":
            name, val = payload
            self.ctx.set(name, val)
        elif kind == "remap":
            name, target_name = payload
            self.ctx.remap(name, target_name)
        else:
            for name in payload:
                self.ctx.invalidate(name)

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)

        try:
            value = self.eval(node.value)
            rhs_val = UNRESOLVED if value is None else value
            plans: list[tuple[str, Any]] = []

            for target in node.targets:
                if isinstance(target, ast.Name):
                    plans.append(self._plan_bind(target, node.value, evaluated=rhs_val))
                elif isinstance(target, (ast.Tuple, ast.List)) and not any(
                    isinstance(e, ast.Starred) for e in target.elts
                ):
                    if isinstance(node.value, (ast.Tuple, ast.List)) and len(
                        target.elts
                    ) == len(node.value.elts):
                        for tgt, val_node in zip(target.elts, node.value.elts):
                            plans.append(self._plan_bind(tgt, val_node))
                    elif value is not None:
                        unwrapped = self.unwrap(value)
                        if isinstance(unwrapped, (tuple, list)) and len(
                            target.elts
                        ) == len(unwrapped):
                            for tgt, elem in zip(target.elts, unwrapped):
                                plans.append(self._plan_bind(tgt, None, evaluated=elem))
                        else:
                            plans.append(
                                ("invalidate", self._collect_target_names(target))
                            )
                    else:
                        plans.append(("invalidate", self._collect_target_names(target)))
                else:
                    plans.append(("invalidate", self._collect_target_names(target)))

            for kind, payload in plans:
                self._apply_bind_plan(kind, payload)
            if any(isinstance(t, ast.Subscript) for t in node.targets):
                self._invalidate_mutable_aliases()

        except Exception:
            for target in node.targets:
                for name in self._collect_target_names(target):
                    self.ctx.invalidate(name)

        return node

    def _visit_stmt_list(self, stmts: list[ast.stmt]) -> list[ast.stmt]:
        new_stmts: list[ast.stmt] = []
        for stmt in stmts:
            res = self.visit(stmt)
            if isinstance(res, list):
                new_stmts.extend(res)
            elif res is not None:
                new_stmts.append(res)
        return new_stmts

    def visit_If(self, node: ast.If):
        node.test = self.visit(node.test)

        old_ctx = self.ctx
        assigned = self._collect_assigned_names(node.body) | self._collect_assigned_names(
            node.orelse
        )

        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self._visit_stmt_list(node.body)

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)
        return node

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While):
        assigned = self._collect_assigned_names(node.body) | self._collect_assigned_names(
            node.orelse
        )
        if isinstance(node, (ast.For, ast.AsyncFor)):
            node.iter = self.visit(node.iter)
            assigned.update(self._collect_target_names(node.target))

        for name in assigned:
            self.ctx.invalidate(name)

        if isinstance(node, ast.While):
            node.test = self.visit(node.test)

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
        return node

    def visit_For(self, node: ast.For):
        return self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        return self._visit_loop(node)

    def visit_While(self, node: ast.While):
        return self._visit_loop(node)

    def visit_Try(self, node: ast.Try | Any):
        body_assigned = self._collect_assigned_names(node.body)
        orelse_assigned = self._collect_assigned_names(node.orelse)
        handler_assigned: set[str] = set()
        for handler in node.handlers:
            if handler.name:
                handler_assigned.add(handler.name)
            handler_assigned.update(self._collect_assigned_names(handler.body))
        assigned = (
            body_assigned
            | orelse_assigned
            | handler_assigned
            | self._collect_assigned_names(node.finalbody)
        )

        old_ctx = self.ctx
        branch_invalidated: set[str] = set()
        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self._visit_stmt_list(node.body)
        branch_invalidated.update(body_ctx.invalidated)

        for handler in node.handlers:
            handler_ctx = Context(parent=old_ctx)
            self.ctx = handler_ctx
            for name in body_assigned:
                self.ctx.invalidate(name)
            if handler.name:
                self.ctx.invalidate(handler.name)
            if handler.type is not None:
                handler.type = self.visit(handler.type)
            handler.body = self._visit_stmt_list(handler.body)
            branch_invalidated.update(handler_ctx.invalidated)

        self.ctx = body_ctx
        node.orelse = self._visit_stmt_list(node.orelse)
        branch_invalidated.update(body_ctx.invalidated)

        final_ctx = Context(parent=old_ctx)
        self.ctx = final_ctx
        for name in body_assigned | orelse_assigned | handler_assigned | branch_invalidated:
            self.ctx.invalidate(name)
        node.finalbody = self._visit_stmt_list(node.finalbody)
        branch_invalidated.update(final_ctx.invalidated)

        self.ctx = old_ctx
        for name in assigned | branch_invalidated:
            self.ctx.invalidate(name)
        return node

    def visit_TryStar(self, node: Any):
        return self.visit_Try(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        res = self._def_visit(node)
        if (
            isinstance(res, ast.FunctionDef)
            and not res.decorator_list
            and len(res.body) == 1
            and isinstance(res.body[0], ast.Return)
            and res.body[0].value is not None
            and not any(
                isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await))
                for n in ast.walk(res.body[0].value)
            )
        ):
            self.ctx.set(res.name, LambdaType(res.body[0].value, res.args))
        return res

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self._def_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        return self._def_visit(node)
