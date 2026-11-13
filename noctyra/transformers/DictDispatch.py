from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from noctyra.core import Context, ImportSymbol, LambdaType
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import IMMUTABLE_TYPES, LOGGER

_SCOPE_NODES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_MUTATING_METHODS = frozenset(
    {
        "append",
        "pop",
        "update",
        "clear",
        "setdefault",
        "extend",
        "insert",
        "remove",
        "reverse",
        "sort",
    }
)

TableValue = dict[Any, Any] | list[Any] | tuple[Any, ...]


def _is_immutable_constant(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, IMMUTABLE_TYPES)


def _extract_const_table(node: ast.AST) -> TableValue | None:
    if isinstance(node, ast.Dict):
        table: dict[Any, Any] = {}
        for key_node, val_node in zip(node.keys, node.values):
            if key_node is None:
                return None
            if not _is_immutable_constant(key_node) or not _is_immutable_constant(
                val_node
            ):
                return None
            assert isinstance(key_node, ast.Constant)
            assert isinstance(val_node, ast.Constant)
            table[key_node.value] = val_node.value
        return table

    if isinstance(node, (ast.List, ast.Tuple)):
        items: list[Any] = []
        for elt in node.elts:
            if not _is_immutable_constant(elt):
                return None
            assert isinstance(elt, ast.Constant)
            items.append(elt.value)
        return items if isinstance(node, ast.List) else tuple(items)

    return None


def _iter_arg_names(args: ast.arguments) -> list[str]:
    names: list[str] = []
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        names.append(arg.arg)
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return names


@dataclass
class _ScopeFrame:
    valid_tables: dict[str, TableValue] = field(default_factory=dict)
    invalidated: set[str] = field(default_factory=set)


class _ScopeAnalyzer:
    """Analyze a single scope and its nested scopes for constant lookup tables."""

    def __init__(self, scope_node: ast.AST) -> None:
        self.scope_node = scope_node
        self.candidates: dict[str, TableValue] = {}
        self.candidate_targets: dict[str, ast.Name] = {}
        self.assign_counts: dict[str, int] = {}
        self.invalidated: set[str] = set()

    def analyze(self) -> _ScopeFrame:
        if isinstance(self.scope_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg_name in _iter_arg_names(self.scope_node.args):
                self.invalidated.add(arg_name)

        self._scan_children(self.scope_node, in_nested_scope=False)

        valid_tables: dict[str, TableValue] = {}
        for name, table in self.candidates.items():
            if name not in self.invalidated and self.assign_counts.get(name, 0) == 1:
                valid_tables[name] = table

        invalidated = set(self.invalidated)
        for name in self.assign_counts:
            if name not in valid_tables:
                invalidated.add(name)

        return _ScopeFrame(valid_tables=valid_tables, invalidated=invalidated)

    def _scan_children(self, node: ast.AST, *, in_nested_scope: bool) -> None:
        for child in ast.iter_child_nodes(node):
            self._scan_node(child, in_nested_scope=in_nested_scope)

    def _scan_node(self, node: ast.AST, *, in_nested_scope: bool) -> None:
        if isinstance(node, _SCOPE_NODES):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.invalidated.add(node.name)
            self._scan_children(node, in_nested_scope=True)
            return

        if not in_nested_scope and isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0]
                name = target.id
                self.assign_counts[name] = self.assign_counts.get(name, 0) + 1
                if self.assign_counts[name] == 1:
                    table = _extract_const_table(node.value)
                    if table is not None:
                        self.candidates[name] = table
                        self.candidate_targets[name] = target
                    else:
                        self.invalidated.add(name)
                else:
                    self.invalidated.add(name)
            self._scan_children(node, in_nested_scope=False)
            return

        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if self.candidate_targets.get(node.id) is not node:
                self.invalidated.add(node.id)

        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and isinstance(node.value, ast.Name)
        ):
            self.invalidated.add(node.value.id)

        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr in _MUTATING_METHODS
        ):
            self.invalidated.add(node.func.value.id)

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname if alias.asname else alias.name.split(".")[0]
                self.invalidated.add(bound)

        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            self.invalidated.add(node.name)

        self._scan_children(node, in_nested_scope=in_nested_scope)


class DictDispatchSimplifier(BaseTransformer):
    """Resolve constant dict/list/tuple lookup tables within a scope."""

    def __init__(self) -> None:
        super().__init__()
        self.max_depth: int = 50
        self.max_allocation: int = 100_000
        self._scope_stack: list[_ScopeFrame] = []

    def _lookup_table(self, name: str) -> TableValue | None:
        for frame in reversed(self._scope_stack):
            if name in frame.valid_tables:
                return frame.valid_tables[name]
            if name in frame.invalidated:
                return None
        return None

    def _visit_scope(self, node: ast.AST, *, create_ctx: bool) -> ast.AST:
        frame = _ScopeAnalyzer(node).analyze()
        self._scope_stack.append(frame)
        old_ctx = self.ctx
        if create_ctx:
            self.ctx = Context(parent=old_ctx)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg_name in _iter_arg_names(node.args):
                    self.ctx.invalidate(arg_name)
        try:
            return self.generic_visit(node)
        finally:
            self.ctx = old_ctx
            self._scope_stack.pop()

    def visit_Module(self, node: ast.Module) -> ast.AST:
        return self._visit_scope(node, create_ctx=False)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_scope(node, create_ctx=True)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_scope(node, create_ctx=True)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        return self._visit_scope(node, create_ctx=True)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.target, ast.Name):
            self.ctx.invalidate(node.target.id)
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.ctx, ast.Load) or not isinstance(node.value, ast.Name):
            return node

        table = self._lookup_table(node.value.id)
        if table is None:
            return node

        key_res = self.eval(node.slice)
        if key_res is None or isinstance(key_res, (LambdaType, ImportSymbol)):
            return node

        key = self.unwrap(key_res)

        if isinstance(table, dict):
            try:
                if key not in table:
                    return node
                val = table[key]
            except TypeError:
                return node
        else:
            if not isinstance(key, int):
                return node
            if not (-len(table) <= key < len(table)):
                return node
            val = table[key]

        LOGGER.debug(f"Folded lookup {node.value.id}[{key!r}] -> {val!r}")
        return ast.copy_location(ast.Constant(value=val), node)
