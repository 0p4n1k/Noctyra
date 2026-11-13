from noctyra.core import LambdaType, ImportSymbol
from noctyra.transformers.safe_eval import safe_eval
from noctyra.core import Context
from typing import Any
import ast


class BaseTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.ctx: Context = Context()

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
        if hasattr(obj, "value"):
            return self.unwrap(obj.value)
        if isinstance(obj, list):
            return [self.unwrap(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self.unwrap(x) for x in obj)
        if isinstance(obj, set):
            return {self.unwrap(x) for x in obj}
        if isinstance(obj, dict):
            return {self.unwrap(k): self.unwrap(v) for k, v in obj.items()}
        return obj

    def _collect_target_names(self, target: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                names.update(self._collect_target_names(elt))
        elif isinstance(target, ast.Starred):
            names.update(self._collect_target_names(target.value))
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
                    elif isinstance(stmt, ast.ImportFrom):
                        for alias in stmt.names:
                            if alias.name != "*":
                                locals_set.add(alias.asname or alias.name)
                    for child in ast.iter_child_nodes(stmt):
                        if isinstance(child, ast.NamedExpr):
                            locals_set.add(child.target.id)
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

    def _def_visit(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        old_ctx = self.ctx

        self.ctx = Context(parent=old_ctx)

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for local_name in self._collect_func_locals(node):
                self.ctx.invalidate(local_name)

        result = self.generic_visit(node)

        self.ctx = old_ctx
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
        old_ctx = self.ctx
        self.ctx = Context(parent=old_ctx)
        generators = getattr(node, "generators", [])
        for comp in generators:
            for name in self._collect_target_names(comp.target):
                self.ctx.invalidate(name)
        result = self.generic_visit(node)
        self.ctx = old_ctx
        return result

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

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)

        try:
            value = self.eval(node.value)

            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Lambda):
                        self.ctx.set(
                            target.id, LambdaType(node.value.body, node.value.args)
                        )

                    elif value is not None:
                        self.ctx.set(target.id, value)

                    elif isinstance(node.value, ast.Name):
                        self.ctx.remap(target.id, node.value.id)
                    else:
                        self.ctx.invalidate(target.id)
                else:
                    for name in self._collect_target_names(target):
                        self.ctx.invalidate(name)

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

        self.ctx = Context(parent=old_ctx)
        node.body = self._visit_stmt_list(node.body)

        self.ctx = Context(parent=old_ctx)
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned:
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
        self.ctx = Context(parent=old_ctx)
        node.body = self._visit_stmt_list(node.body)

        self.ctx = Context(parent=old_ctx)
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned:
            self.ctx.invalidate(name)
        return node

    def visit_For(self, node: ast.For):
        return self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        return self._visit_loop(node)

    def visit_While(self, node: ast.While):
        return self._visit_loop(node)

    def visit_Try(self, node: ast.Try):
        assigned = (
            self._collect_assigned_names(node.body)
            | self._collect_assigned_names(node.orelse)
            | self._collect_assigned_names(node.finalbody)
        )
        for handler in node.handlers:
            if handler.name:
                assigned.add(handler.name)
            assigned.update(self._collect_assigned_names(handler.body))

        old_ctx = self.ctx
        self.ctx = Context(parent=old_ctx)
        node.body = self._visit_stmt_list(node.body)

        for handler in node.handlers:
            self.ctx = Context(parent=old_ctx)
            if handler.name:
                self.ctx.invalidate(handler.name)
            if handler.type is not None:
                handler.type = self.visit(handler.type)
            handler.body = self._visit_stmt_list(handler.body)

        self.ctx = Context(parent=old_ctx)
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = Context(parent=old_ctx)
        node.finalbody = self._visit_stmt_list(node.finalbody)

        self.ctx = old_ctx
        for name in assigned:
            self.ctx.invalidate(name)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        return self._def_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self._def_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        return self._def_visit(node)
