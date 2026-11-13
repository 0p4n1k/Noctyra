from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
import ast
import builtins
import keyword
import re

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER

RenameMode = Literal["all", "obfuscated", "none"]

_BUILTINS = frozenset(dir(builtins))
_LOOKALIKE_CHARS = frozenset("O0l1I_")
_HEX_NAME_RE = re.compile(r"^_?0x[0-9a-fA-F]+$")
_CANONICAL_RE = re.compile(r"^(var|arg|func|cls)_\d+$")


def is_obfuscated_name(name: str) -> bool:
    if not name.isascii():
        return True
    if len(name) >= 2 and set(name) <= _LOOKALIKE_CHARS:
        return True
    if _HEX_NAME_RE.match(name):
        return True
    if name.count("_") >= 3 and len(name) >= 10:
        return True
    if len(name) >= 24 and not re.search(r"[a-z]{3,}", name):
        return True
    return False


def is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


@dataclass
class _Scope:
    node: ast.AST
    kind: Literal["module", "function", "class", "comp"]
    parent: _Scope | None = None
    in_class: bool = False
    original_name: str | None = None
    bindings: dict[str, str] = field(default_factory=dict)  # name -> symbol_kind
    protected: set[str] = field(default_factory=set)
    globals_declared: set[str] = field(default_factory=set)
    nonlocals_declared: set[str] = field(default_factory=set)
    mapping: dict[str, str] = field(default_factory=dict)
    children: dict[int, _Scope] = field(default_factory=dict)  # id(node) -> _Scope


class _ScopeCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.module_scope: _Scope | None = None
        self.current: _Scope | None = None
        self.scopes_by_node: dict[int, _Scope] = {}

    def _enter_scope(
        self,
        node: ast.AST,
        kind: Literal["module", "function", "class", "comp"],
        in_class: bool = False,
    ) -> _Scope:
        scope = _Scope(node=node, kind=kind, parent=self.current, in_class=in_class)
        if self.current is not None:
            self.current.children[id(node)] = scope
        else:
            self.module_scope = scope
        self.scopes_by_node[id(node)] = scope
        self.current = scope
        return scope

    def _exit_scope(self, prev: _Scope | None) -> None:
        self.current = prev

    def _bind(self, name: str, symbol_kind: str = "var") -> None:
        if self.current is None:
            return
        if name in self.current.globals_declared and self.module_scope is not None:
            self.module_scope.bindings.setdefault(name, symbol_kind)
            return
        if name in self.current.nonlocals_declared:
            return
        # Keep the more specific kind if already bound (e.g. func/cls/arg over var)
        existing = self.current.bindings.get(name)
        if existing is None or existing == "var":
            self.current.bindings[name] = symbol_kind

    def _bind_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self._bind(target.id, "var")
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind_target(elt)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value)

    def visit_Module(self, node: ast.Module) -> None:
        prev = self.current
        self._enter_scope(node, "module")
        self.generic_visit(node)
        self._exit_scope(prev)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._bind(node.name, "func")
        for dec in node.decorator_list:
            self.visit(dec)
        for default in node.args.defaults:
            self.visit(default)
        for kw_default in node.args.kw_defaults:
            if kw_default is not None:
                self.visit(kw_default)
        if node.returns is not None:
            self.visit(node.returns)

        in_class_method = self.current is not None and self.current.kind == "class"
        prev = self.current
        func_scope = self._enter_scope(node, "function")
        func_scope.original_name = node.name

        all_args: list[ast.arg] = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        if node.args.vararg is not None:
            all_args.append(node.args.vararg)
        if node.args.kwarg is not None:
            all_args.append(node.args.kwarg)

        for idx, arg in enumerate(all_args):
            if in_class_method and idx == 0 and arg.arg in ("self", "cls"):
                func_scope.protected.add(arg.arg)
            else:
                self._bind(arg.arg, "arg")
            if arg.annotation is not None:
                self.visit(arg.annotation)

        for stmt in node.body:
            self.visit(stmt)

        self._exit_scope(prev)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in node.args.defaults:
            self.visit(default)
        for kw_default in node.args.kw_defaults:
            if kw_default is not None:
                self.visit(kw_default)

        prev = self.current
        self._enter_scope(node, "function")

        all_args: list[ast.arg] = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        if node.args.vararg is not None:
            all_args.append(node.args.vararg)
        if node.args.kwarg is not None:
            all_args.append(node.args.kwarg)

        for arg in all_args:
            self._bind(arg.arg, "arg")

        self.visit(node.body)
        self._exit_scope(prev)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name, "cls")
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw)

        prev = self.current
        self._enter_scope(node, "class", in_class=True)
        for stmt in node.body:
            self.visit(stmt)
        self._exit_scope(prev)

    def _visit_comp(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ) -> None:
        if node.generators:
            self.visit(node.generators[0].iter)

        prev = self.current
        self._enter_scope(node, "comp")

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

        self._exit_scope(prev)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comp(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comp(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comp(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comp(node)

    def visit_Global(self, node: ast.Global) -> None:
        if self.current is not None:
            self.current.globals_declared.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        if self.current is not None:
            self.current.nonlocals_declared.update(node.names)

    def visit_Import(self, node: ast.Import) -> None:
        if self.current is None:
            return
        for alias in node.names:
            if alias.asname:
                self._bind(alias.asname, "var")
            else:
                top_name = alias.name.split(".")[0]
                self.current.protected.add(top_name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.current is None:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            if alias.asname:
                self._bind(alias.asname, "var")
            else:
                self.current.protected.add(alias.name)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._bind_target(target)
            self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)
        if node.simple or isinstance(node.target, ast.Name):
            self._bind_target(node.target)
        self.visit(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self._bind_target(node.target)
        self.visit(node.target)

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
                self.visit(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars)
                self.visit(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self._bind(node.name, "var")
        for stmt in node.body:
            self.visit(stmt)


class IdentifierRenamer(BaseTransformer):
    """Scope-aware identifier normalizer for deobfuscation."""

    def __init__(self, mode: RenameMode = "all") -> None:
        super().__init__()
        self.mode: RenameMode = mode
        self._counters: dict[str, int] = {"var": 0, "arg": 0, "func": 0, "cls": 0}
        self._used_names: set[str] = set()
        self._scopes_by_node: dict[int, _Scope] = {}
        self._module_scope: _Scope | None = None
        self._current_scope: _Scope | None = None
        self._func_param_maps: dict[tuple[int, str], dict[str, str]] = {}

    def _should_rename(self, name: str, scope: _Scope) -> bool:
        if self.mode == "none":
            return False
        if scope.kind == "class":
            return False
        if not name or keyword.iskeyword(name) or keyword.issoftkeyword(name):
            return False
        if is_dunder(name) or name in _BUILTINS or name in scope.protected:
            return False
        if self.mode == "obfuscated":
            return is_obfuscated_name(name)
        return True

    def _next_name(self, symbol_kind: str) -> str:
        prefix = symbol_kind if symbol_kind in self._counters else "var"
        while True:
            self._counters[prefix] += 1
            candidate = f"{prefix}_{self._counters[prefix]}"
            if candidate not in self._used_names:
                self._used_names.add(candidate)
                return candidate

    def _collect_kept_names(self, scope: _Scope) -> None:
        for name in scope.protected:
            self._used_names.add(name)
        for name in scope.bindings:
            if not self._should_rename(name, scope):
                self._used_names.add(name)
        for child in scope.children.values():
            self._collect_kept_names(child)

    def _assign_mappings(self, scope: _Scope) -> None:
        for name, symbol_kind in scope.bindings.items():
            if self._should_rename(name, scope):
                if _CANONICAL_RE.match(name) and name not in self._used_names:
                    self._used_names.add(name)
                    scope.mapping[name] = name
                else:
                    new_name = self._next_name(symbol_kind)
                    scope.mapping[name] = new_name
                    LOGGER.debug(f"Renaming {symbol_kind} '{name}' -> '{new_name}'")

        for child in scope.children.values():
            self._assign_mappings(child)

    def _resolve_name(self, name: str, scope: _Scope | None) -> str | None:
        if scope is None:
            return None

        if name in scope.globals_declared:
            if self._module_scope is not None:
                return self._module_scope.mapping.get(name)
            return None

        if name in scope.mapping:
            return scope.mapping[name]

        if name in scope.protected or name in scope.bindings:
            return None

        # Walk enclosing scopes (skipping class scopes per Python LEGB rules)
        cur = scope.parent
        while cur is not None:
            if cur.kind != "class":
                if name in cur.mapping:
                    return cur.mapping[name]
                if name in cur.protected or name in cur.bindings:
                    return None
            cur = cur.parent

        return None

    def _resolve_func_scope(
        self, func_name: str, scope: _Scope | None
    ) -> _Scope | None:
        cur = scope
        while cur is not None:
            if cur.kind != "class" or cur is scope:
                for child in cur.children.values():
                    if (
                        isinstance(child.node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and child.original_name == func_name
                    ):
                        return child
            cur = cur.parent
        return None

    def visit_Module(self, node: ast.Module) -> ast.AST:
        if self.mode == "none":
            return node

        self._counters = {"var": 0, "arg": 0, "func": 0, "cls": 0}
        self._used_names = set(_BUILTINS)
        self._func_param_maps = {}

        collector = _ScopeCollector()
        collector.visit(node)

        self._scopes_by_node = collector.scopes_by_node
        self._module_scope = collector.module_scope

        if self._module_scope is not None:
            self._collect_kept_names(self._module_scope)
            self._assign_mappings(self._module_scope)

        self._current_scope = self._module_scope
        result = self.generic_visit(node)
        ast.fix_missing_locations(result)
        return result

    def _visit_func_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
        enclosing = self._current_scope
        if enclosing is not None and node.name in enclosing.mapping:
            node.name = enclosing.mapping[node.name]

        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        node.args.defaults = [self.visit(d) for d in node.args.defaults]
        node.args.kw_defaults = [
            self.visit(d) if d is not None else None for d in node.args.kw_defaults
        ]
        if node.returns is not None:
            node.returns = self.visit(node.returns)

        func_scope = self._scopes_by_node.get(id(node))
        prev = self._current_scope
        if func_scope is not None:
            self._current_scope = func_scope

        all_args: list[ast.arg] = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        if node.args.vararg is not None:
            all_args.append(node.args.vararg)
        if node.args.kwarg is not None:
            all_args.append(node.args.kwarg)

        for arg in all_args:
            if func_scope is not None and arg.arg in func_scope.mapping:
                arg.arg = func_scope.mapping[arg.arg]
            if arg.annotation is not None:
                arg.annotation = self.visit(arg.annotation)

        node.body = [self.visit(stmt) for stmt in node.body]
        self._current_scope = prev
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_func_def(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_func_def(node)

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        node.args.defaults = [self.visit(d) for d in node.args.defaults]
        node.args.kw_defaults = [
            self.visit(d) if d is not None else None for d in node.args.kw_defaults
        ]

        func_scope = self._scopes_by_node.get(id(node))
        prev = self._current_scope
        if func_scope is not None:
            self._current_scope = func_scope

        all_args: list[ast.arg] = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        if node.args.vararg is not None:
            all_args.append(node.args.vararg)
        if node.args.kwarg is not None:
            all_args.append(node.args.kwarg)

        for arg in all_args:
            if func_scope is not None and arg.arg in func_scope.mapping:
                arg.arg = func_scope.mapping[arg.arg]

        node.body = self.visit(node.body)
        self._current_scope = prev
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        enclosing = self._current_scope
        if enclosing is not None and node.name in enclosing.mapping:
            node.name = enclosing.mapping[node.name]

        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        node.bases = [self.visit(b) for b in node.bases]
        node.keywords = [self.visit(k) for k in node.keywords]

        cls_scope = self._scopes_by_node.get(id(node))
        prev = self._current_scope
        if cls_scope is not None:
            self._current_scope = cls_scope

        node.body = [self.visit(stmt) for stmt in node.body]
        self._current_scope = prev
        return node

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

    def visit_Name(self, node: ast.Name) -> ast.AST:
        new_name = self._resolve_name(node.id, self._current_scope)
        if new_name is not None:
            return ast.copy_location(ast.Name(id=new_name, ctx=node.ctx), node)
        return node

    def visit_Global(self, node: ast.Global) -> ast.AST:
        if self._module_scope is not None:
            node.names = [self._module_scope.mapping.get(n, n) for n in node.names]
        return node

    def visit_Nonlocal(self, node: ast.Nonlocal) -> ast.AST:
        node.names = [
            self._resolve_name(n, self._current_scope) or n for n in node.names
        ]
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        if node.name:
            new_name = self._resolve_name(node.name, self._current_scope)
            if new_name is not None:
                node.name = new_name
        return self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> ast.AST:
        return self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        return self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> ast.AST:
        if node.asname and self._current_scope is not None:
            new_name = self._current_scope.mapping.get(node.asname)
            if new_name is not None:
                node.asname = new_name
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        target_scope: _Scope | None = None
        if isinstance(node.func, ast.Name):
            target_scope = self._resolve_func_scope(node.func.id, self._current_scope)

        node.func = self.visit(node.func)
        node.args = [self.visit(a) for a in node.args]
        for kw in node.keywords:
            if kw.arg is not None and target_scope is not None:
                if kw.arg in target_scope.mapping:
                    kw.arg = target_scope.mapping[kw.arg]
            kw.value = self.visit(kw.value)
        return node
