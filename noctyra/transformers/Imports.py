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
                self.current.aliases[alias.asname] = alias.name
            else:
                self._bind(alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.current is None:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            if alias.asname:
                self.current.aliases[alias.asname] = alias.name
            else:
                self._bind(alias.name)

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

    def _compute_unfolds(self, scope: _ImportScope) -> None:
        unfolds: dict[str, str] = {}
        seen_targets: set[str] = set()
        for asname, target in scope.aliases.items():
            if asname in scope.reassigned:
                continue
            top_target = target.split(".")[0]
            if keyword.iskeyword(top_target) or keyword.issoftkeyword(top_target):
                continue
            if top_target in scope.bound_names:
                continue
            if top_target in scope.aliases and scope.aliases[top_target] != target:
                continue
            if top_target in seen_targets and target != top_target:
                continue
            unfolds[asname] = target
            seen_targets.add(top_target)
        self._active_unfolds[id(scope)] = unfolds
        for child in scope.children.values():
            self._compute_unfolds(child)

    def _resolve_unfold(self, name: str, scope: _ImportScope | None) -> str | None:
        cur = scope
        while cur is not None:
            unfolds = self._active_unfolds.get(id(cur), {})
            if name in unfolds:
                return unfolds[name]
            if name in cur.bound_names or name in cur.aliases:
                return None
            cur = cur.parent
            while cur is not None and cur.is_class:
                cur = cur.parent
        return None

    def visit_Module(self, node: ast.Module) -> ast.AST:
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
