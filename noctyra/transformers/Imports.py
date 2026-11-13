from __future__ import annotations

import ast
import keyword
from dataclasses import dataclass, field

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _build_attr_chain(dotted: str, ctx: ast.expr_context, orig: ast.AST) -> ast.expr:
    parts = dotted.split(".")
    node: ast.expr = ast.copy_location(
        ast.Name(id=parts[0], ctx=ast.Load() if len(parts) > 1 else ctx), orig
    )
    for idx, part in enumerate(parts[1:]):
        part_ctx = ctx if idx == len(parts) - 2 else ast.Load()
        node = ast.copy_location(
            ast.Attribute(value=node, attr=part, ctx=part_ctx), orig
        )
    return node


@dataclass
class _ImportScope:
    parent: _ImportScope | None = None
    is_class: bool = False
    aliases: dict[str, str] = field(
        default_factory=dict
    )  # asname -> target dotted name
    alias_sources: dict[str, str] = field(
        default_factory=dict
    )  # asname -> origin key for collision detection
    globals_declared: set[str] = field(default_factory=set)
    bound_names: set[str] = field(default_factory=set)
    reassigned: set[str] = field(default_factory=set)
    children: dict[int, _ImportScope] = field(default_factory=dict)


class _ImportAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.root: _ImportScope | None = None
        self.current: _ImportScope | None = None
        self.scopes_by_node: dict[int, _ImportScope] = {}

    def _enter(self, node: ast.AST, is_class: bool = False) -> _ImportScope:
        scope = _ImportScope(parent=self.current, is_class=is_class)
        if self.current is not None:
            self.current.children[id(node)] = scope
        else:
            self.root = scope
        self.scopes_by_node[id(node)] = scope
        self.current = scope
        return scope

    def _bind(self, name: str) -> None:
        if self.current is None:
            return
        if name in self.current.globals_declared and self.root is not None:
            if name in self.root.aliases:
                self.root.reassigned.add(name)
            self.root.bound_names.add(name)
            return
        if name in self.current.aliases:
            self.current.reassigned.add(name)
        self.current.bound_names.add(name)

    def _bind_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self._bind(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind_target(elt)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value)

    def visit_Module(self, node: ast.Module) -> None:
        prev = self.current
        self._enter(node)
        self.generic_visit(node)
        self.current = prev

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._bind(node.name)
        for dec in node.decorator_list:
            self.visit(dec)
        for d in node.args.defaults:
            self.visit(d)
        for kw_d in node.args.kw_defaults:
            if kw_d is not None:
                self.visit(kw_d)
        if node.returns is not None:
            self.visit(node.returns)

        prev = self.current
        self._enter(node)
        for arg in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        ):
            self._bind(arg.arg)
        if node.args.vararg is not None:
            self._bind(node.args.vararg.arg)
        if node.args.kwarg is not None:
            self._bind(node.args.kwarg.arg)
        for stmt in node.body:
            self.visit(stmt)
        self.current = prev

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in node.args.defaults:
            self.visit(d)
        for kw_d in node.args.kw_defaults:
            if kw_d is not None:
                self.visit(kw_d)
        prev = self.current
        self._enter(node)
        for arg in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        ):
            self._bind(arg.arg)
        if node.args.vararg is not None:
            self._bind(node.args.vararg.arg)
        if node.args.kwarg is not None:
            self._bind(node.args.kwarg.arg)
        self.visit(node.body)
        self.current = prev

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name)
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw)
        prev = self.current
        self._enter(node, is_class=True)
        for stmt in node.body:
            self.visit(stmt)
        self.current = prev

    def _visit_comp(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        if node.generators:
            self.visit(node.generators[0].iter)
        prev = self.current
        self._enter(node)
        for idx, gen in enumerate(node.generators):
            if idx > 0:
                self.visit(gen.iter)
            self._bind_target(gen.target)
            for if_expr in gen.ifs:
                self.visit(if_expr)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            if node.value is not None:
                self.visit(node.value)
        else:
            self.visit(node.elt)
        self.current = prev

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comp(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comp(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comp(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comp(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self.current is None:
            return
        for alias in node.names:
            if alias.asname:
                target_scope = (
                    self.root
                    if alias.asname in self.current.globals_declared
                    and self.root is not None
                    else self.current
                )
                target_scope.aliases[alias.asname] = alias.name
                target_scope.alias_sources[alias.asname] = f"import:{alias.name.split('.')[0]}"
            else:
                self._bind(alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.current is None:
            return
        mod = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                continue
            if alias.asname:
                target_scope = (
                    self.root
                    if alias.asname in self.current.globals_declared
                    and self.root is not None
                    else self.current
                )
                target_scope.aliases[alias.asname] = alias.name
                target_scope.alias_sources[alias.asname] = (
                    f"from:{node.level}:{mod}:{alias.name}"
                )
            else:
                self._bind(alias.name)

    def visit_Global(self, node: ast.Global) -> None:
        if self.current is not None:
            self.current.globals_declared.update(node.names)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._bind_target(target)
            self.visit(target)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._bind_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)
        if node.simple or isinstance(node.target, ast.Name):
            self._bind_target(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self._bind_target(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._bind_target(node.target)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self._bind_target(node.target)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.iter)
        self._bind_target(node.target)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self._bind(node.name)
        for stmt in node.body:
            self.visit(stmt)


class ImportAliasFolder(BaseTransformer):
    """Unfold aliased imports (`import m as a`) into `import m` and replace usages."""

    def __init__(self) -> None:
        super().__init__()
        self._scopes_by_node: dict[int, _ImportScope] = {}
        self._current_scope: _ImportScope | None = None
        self._active_unfolds: dict[int, dict[str, str]] = {}

    def _descendant_shadows(
        self, scope: _ImportScope, top_target: str, source_key: str
    ) -> bool:
        for child in scope.children.values():
            if top_target in child.bound_names:
                return True
            if (
                top_target in child.aliases
                and child.alias_sources.get(top_target) != source_key
            ):
                return True
            if self._descendant_shadows(child, top_target, source_key):
                return True
        return False

    def _compute_unfolds(self, scope: _ImportScope) -> None:
        unfolds: dict[str, str] = {}
        seen_sources: dict[str, str] = {}
        for asname, target in scope.aliases.items():
            if asname in scope.reassigned:
                continue
            top_target = target.split(".")[0]
            source_key = scope.alias_sources.get(asname, f"import:{top_target}")
            if keyword.iskeyword(top_target) or keyword.issoftkeyword(top_target):
                continue
            if top_target in scope.bound_names:
                continue
            if (
                top_target in scope.aliases
                and scope.alias_sources.get(top_target) != source_key
            ):
                continue
            if (
                top_target in seen_sources
                and seen_sources[top_target] != source_key
            ):
                continue
            if self._descendant_shadows(scope, top_target, source_key):
                continue
            unfolds[asname] = target
            seen_sources[top_target] = source_key
        self._active_unfolds[id(scope)] = unfolds
        for child in scope.children.values():
            self._compute_unfolds(child)

    def _resolve_unfold(self, name: str, scope: _ImportScope | None) -> str | None:
        cur = scope
        traversed: list[_ImportScope] = []
        while cur is not None:
            unfolds = self._active_unfolds.get(id(cur), {})
            if name in unfolds:
                target = unfolds[name]
                top_target = target.split(".")[0]
                source_key = cur.alias_sources.get(name, f"import:{top_target}")
                for mid in traversed:
                    if top_target in mid.bound_names:
                        return None
                    if (
                        top_target in mid.aliases
                        and mid.alias_sources.get(top_target) != source_key
                    ):
                        return None
                return target
            if name in cur.bound_names or name in cur.aliases:
                return None
            traversed.append(cur)
            cur = cur.parent
            while cur is not None and cur.is_class:
                traversed.append(cur)
                cur = cur.parent
        return None

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self._active_unfolds = {}
        self._scopes_by_node = {}
        analyzer = _ImportAnalyzer()
        analyzer.visit(node)
        self._scopes_by_node = analyzer.scopes_by_node
        if analyzer.root is not None:
            self._compute_unfolds(analyzer.root)
        self._current_scope = analyzer.root
        result = self.generic_visit(node)
        ast.fix_missing_locations(result)
        return result

    def _visit_scoped(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
    ) -> ast.AST:
        next_scope = self._scopes_by_node.get(id(node))
        prev = self._current_scope
        if next_scope is not None:
            self._current_scope = next_scope
        result = self.generic_visit(node)
        self._current_scope = prev
        return result

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_scoped(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_scoped(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        return self._visit_scoped(node)

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        return self._visit_scoped(node)

    def _visit_comp_node(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ) -> ast.AST:
        if node.generators:
            node.generators[0].iter = self.visit(node.generators[0].iter)
        comp_scope = self._scopes_by_node.get(id(node))
        prev = self._current_scope
        if comp_scope is not None:
            self._current_scope = comp_scope
        for idx, gen in enumerate(node.generators):
            if idx > 0:
                gen.iter = self.visit(gen.iter)
            gen.target = self.visit(gen.target)
            gen.ifs = [self.visit(if_expr) for if_expr in gen.ifs]
        if isinstance(node, ast.DictComp):
            node.key = self.visit(node.key)
            if node.value is not None:
                node.value = self.visit(node.value)
        else:
            node.elt = self.visit(node.elt)
        self._current_scope = prev
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        return self._visit_comp_node(node)

    def visit_SetComp(self, node: ast.SetComp) -> ast.AST:
        return self._visit_comp_node(node)

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        return self._visit_comp_node(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.AST:
        return self._visit_comp_node(node)

    def visit_Import(self, node: ast.Import) -> ast.AST:
        if self._current_scope is not None:
            unfolds = self._active_unfolds.get(id(self._current_scope), {})
            for alias in node.names:
                if alias.asname and alias.asname in unfolds:
                    LOGGER.debug(
                        f"Unfolding import alias: {alias.name} as {alias.asname} -> {alias.name}"
                    )
                    alias.asname = None
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        if self._current_scope is not None:
            unfolds = self._active_unfolds.get(id(self._current_scope), {})
            for alias in node.names:
                if alias.asname and alias.asname in unfolds:
                    LOGGER.debug(
                        f"Unfolding from-import alias: {alias.name} as {alias.asname} -> {alias.name}"
                    )
                    alias.asname = None
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        return self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load):
            target = self._resolve_unfold(node.id, self._current_scope)
            if target is not None:
                return _build_attr_chain(target, node.ctx, node)
        return node


class SwappedImportResolver(BaseTransformer):
    """Rename imports that are reassigned/swapped in the same scope to collision-free aliases."""

    def _collect_all_names(self, stmts: list[ast.stmt]) -> set[str]:
        names: set[str] = set()
        for stmt in stmts:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Name):
                    names.add(child.id)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(child.name)
                elif isinstance(child, ast.alias):
                    names.add(child.asname or child.name.split(".")[0])
                elif isinstance(child, ast.arg):
                    names.add(child.arg)
        return names

    def _collect_scope_imports_and_rebindings(
        self, stmts: list[ast.stmt]
    ) -> tuple[set[str], set[str]]:
        imported: set[str] = set()
        rebound: set[str] = set()

        def _walk(body: list[ast.stmt]) -> None:
            for stmt in body:
                if isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        if "." not in alias.name and (
                            alias.asname is None or alias.asname == alias.name
                        ):
                            imported.add(alias.name)
                elif isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        rebound.update(self._collect_target_names(t))
                    self._collect_nested_walrus(stmt.value, rebound)
                elif isinstance(stmt, ast.AugAssign):
                    rebound.update(self._collect_target_names(stmt.target))
                    self._collect_nested_walrus(stmt.value, rebound)
                elif isinstance(stmt, ast.AnnAssign):
                    rebound.update(self._collect_target_names(stmt.target))
                    if stmt.value is not None:
                        self._collect_nested_walrus(stmt.value, rebound)
                elif isinstance(stmt, ast.Delete):
                    for t in stmt.targets:
                        rebound.update(self._collect_target_names(t))
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    rebound.add(stmt.name)
                    continue
                elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                    rebound.update(self._collect_target_names(stmt.target))
                    _walk(stmt.body)
                    _walk(stmt.orelse)
                elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                    for item in stmt.items:
                        if item.optional_vars is not None:
                            rebound.update(self._collect_target_names(item.optional_vars))
                    _walk(stmt.body)
                elif isinstance(stmt, ast.If):
                    _walk(stmt.body)
                    _walk(stmt.orelse)
                elif isinstance(stmt, ast.While):
                    _walk(stmt.body)
                    _walk(stmt.orelse)
                elif isinstance(stmt, ast.Try):
                    _walk(stmt.body)
                    for h in stmt.handlers:
                        if h.name:
                            rebound.add(h.name)
                        _walk(h.body)
                    _walk(stmt.orelse)
                    _walk(stmt.finalbody)
                else:
                    self._collect_nested_walrus(stmt, rebound)

        _walk(stmts)
        return imported, rebound

    def _rewrite_expr(self, expr: ast.AST, active: dict[str, str]) -> ast.AST:
        if not active:
            return expr
        collect_targets = self._collect_target_names

        class _ExprRewriter(ast.NodeTransformer):
            def __init__(self) -> None:
                self._shadowed: list[set[str]] = []

            def visit_FunctionDef(self, n: ast.FunctionDef) -> ast.AST:
                return n

            def visit_AsyncFunctionDef(self, n: ast.AsyncFunctionDef) -> ast.AST:
                return n

            def visit_ClassDef(self, n: ast.ClassDef) -> ast.AST:
                return n

            def visit_Lambda(self, n: ast.Lambda) -> ast.AST:
                n.args.defaults = [self.visit(d) for d in n.args.defaults]
                n.args.kw_defaults = [
                    self.visit(d) if d is not None else None
                    for d in n.args.kw_defaults
                ]
                params: set[str] = {
                    a.arg
                    for a in (
                        list(n.args.posonlyargs)
                        + list(n.args.args)
                        + list(n.args.kwonlyargs)
                    )
                }
                if n.args.vararg is not None:
                    params.add(n.args.vararg.arg)
                if n.args.kwarg is not None:
                    params.add(n.args.kwarg.arg)
                self._shadowed.append(params)
                try:
                    n.body = self.visit(n.body)
                finally:
                    self._shadowed.pop()
                return n

            def _visit_comp(
                self,
                n: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
            ) -> ast.AST:
                if n.generators:
                    n.generators[0].iter = self.visit(n.generators[0].iter)
                comp_targets: set[str] = set()
                self._shadowed.append(comp_targets)
                try:
                    for idx, gen in enumerate(n.generators):
                        if idx > 0:
                            gen.iter = self.visit(gen.iter)
                        gen.target = self.visit(gen.target)
                        comp_targets.update(collect_targets(gen.target))
                        gen.ifs = [self.visit(if_expr) for if_expr in gen.ifs]
                    if isinstance(n, ast.DictComp):
                        n.key = self.visit(n.key)
                        if n.value is not None:
                            n.value = self.visit(n.value)
                    else:
                        n.elt = self.visit(n.elt)
                finally:
                    self._shadowed.pop()
                return n

            def visit_ListComp(self, n: ast.ListComp) -> ast.AST:
                return self._visit_comp(n)

            def visit_SetComp(self, n: ast.SetComp) -> ast.AST:
                return self._visit_comp(n)

            def visit_DictComp(self, n: ast.DictComp) -> ast.AST:
                return self._visit_comp(n)

            def visit_GeneratorExp(self, n: ast.GeneratorExp) -> ast.AST:
                return self._visit_comp(n)

            def visit_NamedExpr(self, n: ast.NamedExpr) -> ast.AST:
                n.value = self.visit(n.value)
                active.pop(n.target.id, None)
                return n

            def visit_Name(self, n: ast.Name) -> ast.AST:
                if (
                    isinstance(n.ctx, ast.Load)
                    and n.id in active
                    and not any(n.id in s for s in self._shadowed)
                ):
                    return ast.copy_location(
                        ast.Name(id=active[n.id], ctx=n.ctx), n
                    )
                return n

        return _ExprRewriter().visit(expr)

    def _process_stmt_list(
        self,
        stmts: list[ast.stmt],
        colliding: dict[str, str],
        active: dict[str, str],
    ) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name in colliding and (
                        alias.asname is None or alias.asname == alias.name
                    ):
                        safe = colliding[alias.name]
                        LOGGER.debug(
                            f"Renaming colliding import {alias.name} -> {safe}"
                        )
                        alias.asname = safe
                        active[alias.name] = safe
            elif isinstance(stmt, ast.Assign):
                stmt.value = self._rewrite_expr(stmt.value, active)  # type: ignore[assignment]
                stmt.targets = [
                    self._rewrite_expr(t, active) for t in stmt.targets  # type: ignore[misc]
                ]
                for t in stmt.targets:
                    for name in self._collect_target_names(t):
                        active.pop(name, None)
            elif isinstance(stmt, ast.AugAssign):
                stmt.target = self._rewrite_expr(stmt.target, active)  # type: ignore[assignment]
                stmt.value = self._rewrite_expr(stmt.value, active)  # type: ignore[assignment]
                for name in self._collect_target_names(stmt.target):
                    active.pop(name, None)
            elif isinstance(stmt, ast.AnnAssign):
                stmt.target = self._rewrite_expr(stmt.target, active)  # type: ignore[assignment]
                if stmt.value is not None:
                    stmt.value = self._rewrite_expr(stmt.value, active)  # type: ignore[assignment]
                stmt.annotation = self._rewrite_expr(stmt.annotation, active)  # type: ignore[assignment]
                for name in self._collect_target_names(stmt.target):
                    active.pop(name, None)
            elif isinstance(stmt, ast.Delete):
                stmt.targets = [
                    self._rewrite_expr(t, active) for t in stmt.targets  # type: ignore[misc]
                ]
                for t in stmt.targets:
                    for name in self._collect_target_names(t):
                        active.pop(name, None)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stmt.decorator_list = [
                    self._rewrite_expr(d, active) for d in stmt.decorator_list  # type: ignore[misc]
                ]
                stmt.args.defaults = [
                    self._rewrite_expr(d, active) for d in stmt.args.defaults  # type: ignore[misc]
                ]
                stmt.args.kw_defaults = [
                    self._rewrite_expr(d, active) if d is not None else None  # type: ignore[misc]
                    for d in stmt.args.kw_defaults
                ]
                active.pop(stmt.name, None)
                self._process_scope(stmt.body, extra_rebound={
                    a.arg
                    for a in (
                        list(stmt.args.posonlyargs)
                        + list(stmt.args.args)
                        + list(stmt.args.kwonlyargs)
                    )
                })
            elif isinstance(stmt, ast.ClassDef):
                stmt.decorator_list = [
                    self._rewrite_expr(d, active) for d in stmt.decorator_list  # type: ignore[misc]
                ]
                stmt.bases = [self._rewrite_expr(b, active) for b in stmt.bases]  # type: ignore[misc]
                active.pop(stmt.name, None)
                self._process_scope(stmt.body)
            elif isinstance(stmt, ast.If):
                stmt.test = self._rewrite_expr(stmt.test, active)  # type: ignore[assignment]
                assigned = self._collect_assigned_names(
                    stmt.body
                ) | self._collect_assigned_names(stmt.orelse)
                body_active = dict(active)
                else_active = dict(active)
                self._process_stmt_list(stmt.body, colliding, body_active)
                self._process_stmt_list(stmt.orelse, colliding, else_active)
                for name in assigned:
                    active.pop(name, None)
                for branch_active in (body_active, else_active):
                    for k, v in branch_active.items():
                        if k not in assigned and k in colliding:
                            active[k] = v
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                stmt.iter = self._rewrite_expr(stmt.iter, active)  # type: ignore[assignment]
                assigned = self._collect_target_names(stmt.target) | self._collect_assigned_names(
                    stmt.body
                ) | self._collect_assigned_names(stmt.orelse)
                for name in assigned:
                    active.pop(name, None)
                body_active = dict(active)
                else_active = dict(active)
                self._process_stmt_list(stmt.body, colliding, body_active)
                self._process_stmt_list(stmt.orelse, colliding, else_active)
                for branch_active in (body_active, else_active):
                    for k, v in branch_active.items():
                        if k not in assigned and k in colliding:
                            active[k] = v
            elif isinstance(stmt, ast.While):
                assigned = self._collect_assigned_names(
                    stmt.body
                ) | self._collect_assigned_names(stmt.orelse)
                for name in assigned:
                    active.pop(name, None)
                stmt.test = self._rewrite_expr(stmt.test, active)  # type: ignore[assignment]
                body_active = dict(active)
                else_active = dict(active)
                self._process_stmt_list(stmt.body, colliding, body_active)
                self._process_stmt_list(stmt.orelse, colliding, else_active)
                for branch_active in (body_active, else_active):
                    for k, v in branch_active.items():
                        if k not in assigned and k in colliding:
                            active[k] = v
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    item.context_expr = self._rewrite_expr(item.context_expr, active)  # type: ignore[assignment]
                    if item.optional_vars is not None:
                        for name in self._collect_target_names(item.optional_vars):
                            active.pop(name, None)
                self._process_stmt_list(stmt.body, colliding, active)
            elif isinstance(stmt, ast.Try):
                assigned = self._collect_assigned_names(
                    stmt.body
                ) | self._collect_assigned_names(
                    stmt.orelse
                ) | self._collect_assigned_names(stmt.finalbody)
                for h in stmt.handlers:
                    if h.name:
                        assigned.add(h.name)
                    assigned.update(self._collect_assigned_names(h.body))
                try_active = dict(active)
                self._process_stmt_list(stmt.body, colliding, try_active)
                else_active = dict(try_active)
                self._process_stmt_list(stmt.orelse, colliding, else_active)
                h_actives: list[dict[str, str]] = []
                body_assigned = self._collect_assigned_names(stmt.body)
                for h in stmt.handlers:
                    h_active = dict(active)
                    for name in body_assigned:
                        h_active.pop(name, None)
                    if h.name:
                        h_active.pop(h.name, None)
                    self._process_stmt_list(h.body, colliding, h_active)
                    h_actives.append(h_active)
                for name in assigned:
                    active.pop(name, None)
                for branch_active in (try_active, else_active, *h_actives):
                    for k, v in branch_active.items():
                        if k not in assigned and k in colliding:
                            active[k] = v
                final_active = dict(active)
                self._process_stmt_list(stmt.finalbody, colliding, final_active)
                for k, v in final_active.items():
                    if k not in assigned and k in colliding:
                        active[k] = v
            else:
                self._rewrite_expr(stmt, active)

    def _process_scope(
        self, stmts: list[ast.stmt], extra_rebound: set[str] | None = None
    ) -> None:
        imported, rebound = self._collect_scope_imports_and_rebindings(stmts)
        if extra_rebound:
            rebound |= extra_rebound
        collisions = imported & rebound
        if not collisions:
            # Still recurse into nested functions/classes
            for stmt in stmts:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._process_scope(
                        stmt.body,
                        extra_rebound={
                            a.arg
                            for a in (
                                list(stmt.args.posonlyargs)
                                + list(stmt.args.args)
                                + list(stmt.args.kwonlyargs)
                            )
                        },
                    )
                elif isinstance(stmt, ast.ClassDef):
                    self._process_scope(stmt.body)
            return

        all_names = self._collect_all_names(stmts)
        colliding_map: dict[str, str] = {}
        for mod in sorted(collisions):
            candidate = f"_noctyra_mod_{mod}"
            idx = 2
            while candidate in all_names:
                candidate = f"_noctyra_mod_{mod}_{idx}"
                idx += 1
            all_names.add(candidate)
            colliding_map[mod] = candidate

        self._process_stmt_list(stmts, colliding_map, {})

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self._process_scope(node.body)
        ast.fix_missing_locations(node)
        return node

