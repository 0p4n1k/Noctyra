from __future__ import annotations

import ast
import builtins
import keyword
from noctyra.core import ImportSymbol, is_symbolic_ref
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER

_MODULE_DUNDERS = frozenset(
    {
        "__dict__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__path__",
        "__spec__",
        "__cached__",
    }
)
_BUILTIN_ATTRS = frozenset(dir(builtins)) - _MODULE_DUNDERS


class BasicInliner(BaseTransformer):
    """Inline dynamic lookups: globals/locals/builtins subscripts, getattr, __import__."""

    def __init__(self) -> None:
        super().__init__()
        self._needed_imports: list[str] = []

    def _eval_identifier(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return (
                node.value
                if node.value.isidentifier() and not keyword.iskeyword(node.value)
                else None
            )
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

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self._needed_imports = []
        self.generic_visit(node)

        if self._needed_imports:
            existing: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        if not alias.asname:
                            existing.add(alias.name.split(".")[0])
            new_imports: list[ast.stmt] = []
            for mod in self._needed_imports:
                if mod not in existing:
                    existing.add(mod)
                    new_imports.append(
                        ast.Import(names=[ast.alias(name=mod, asname=None)])
                    )
            if new_imports:
                insert_idx = 0
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    insert_idx = 1
                while (
                    insert_idx < len(node.body)
                    and isinstance(node.body[insert_idx], ast.ImportFrom)
                    and getattr(node.body[insert_idx], "module", None) == "__future__"
                ):
                    insert_idx += 1
                body = list(node.body)
                node.body = body[:insert_idx] + new_imports + body[insert_idx:]
                ast.fix_missing_locations(node)

        return node

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

    def _is_pure_seq(self, node: ast.AST) -> bool:
        if isinstance(node, (ast.Name, ast.Constant)):
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return all(self._is_pure_seq(e) for e in node.elts)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("dir", "list", "tuple")
            and not node.keywords
        ):
            return all(self._is_pure_seq(a) for a in node.args)
        return False

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and self._is_builtins_namespace(node.value.id)
            and self._is_builtin_usable(node.attr)
        ):
            if node.attr in _BUILTIN_ATTRS:
                LOGGER.debug(f"Inlined {node.value.id}.{node.attr} -> {node.attr}")
                return ast.copy_location(
                    ast.Name(id=node.attr, ctx=node.ctx), node
                )
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        # Generic identity: seq[seq.index(x)] -> x (for pure seq)
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.slice, ast.Call)
            and isinstance(node.slice.func, ast.Attribute)
            and node.slice.func.attr == "index"
            and len(node.slice.args) == 1
            and not node.slice.keywords
            and self._is_pure_seq(node.value)
            and ast.dump(node.value) == ast.dump(node.slice.func.value)
        ):
            LOGGER.debug("Simplified seq[seq.index(x)] -> x")
            return ast.copy_location(node.slice.args[0], node)

        ident = self._eval_identifier(node.slice)
        if ident is None:
            return node

        # globals()['x'] / locals()['x'] / vars()['x'] (Load or Store, never Del)
        if (
            isinstance(node.ctx, (ast.Load, ast.Store))
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and self.ctx.remap_is(node.value.func.id, ["globals", "locals", "vars"])
            and self.ctx.is_usable(node.value.func.id)
            and not node.value.args
            and not node.value.keywords
        ):
            LOGGER.debug(f"Inlined {node.value.func.id}()[{ident!r}] -> {ident}")
            return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)

        if not isinstance(node.ctx, ast.Load):
            return node

        # __builtins__['print']
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "__builtins__"
            and self._is_builtins_namespace(node.value.id)
            and self._is_builtin_usable(ident)
        ):
            LOGGER.debug(f"Inlined __builtins__[{ident!r}] -> {ident}")
            return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)

        # builtins.__dict__['print']
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
            and isinstance(node.value.value, ast.Name)
            and self._is_builtins_namespace(node.value.value.id)
            and self._is_builtin_usable(ident)
        ):
            LOGGER.debug(f"Inlined builtins.__dict__[{ident!r}] -> {ident}")
            return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)

        # vars(obj)['attr'] -> obj.attr
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and self.ctx.remap_is(node.value.func.id, ["vars"])
            and self.ctx.is_usable(node.value.func.id)
            and len(node.value.args) == 1
            and not node.value.keywords
        ):
            target_obj = node.value.args[0]
            if (
                isinstance(target_obj, ast.Name)
                and self._is_builtins_namespace(target_obj.id)
                and self._is_builtin_usable(ident)
            ):
                LOGGER.debug(f"Inlined vars({target_obj.id})[{ident!r}] -> {ident}")
                return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)
            LOGGER.debug(f"Inlined vars(...)[{ident!r}] -> .{ident}")
            return ast.copy_location(
                ast.Attribute(value=target_obj, attr=ident, ctx=node.ctx), node
            )

        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name) or node.keywords:
            return node

        # getattr(obj, 'attr') -> obj.attr (or attr if obj is builtins/__builtins__)
        if (
            node.func.id == "getattr"
            and self._is_builtin_usable("getattr")
            and len(node.args) == 2
        ):
            attr_name = self._eval_identifier(node.args[1])
            if attr_name is not None:
                obj = node.args[0]
                if (
                    isinstance(obj, ast.Name)
                    and self._is_builtins_namespace(obj.id)
                    and attr_name in _BUILTIN_ATTRS
                    and self._is_builtin_usable(attr_name)
                ):
                    LOGGER.debug(
                        f"Inlined getattr({obj.id}, {attr_name!r}) -> {attr_name}"
                    )
                    return ast.copy_location(
                        ast.Name(id=attr_name, ctx=ast.Load()), node
                    )
                LOGGER.debug(f"Inlined getattr(..., {attr_name!r}) -> .{attr_name}")
                return ast.copy_location(
                    ast.Attribute(value=obj, attr=attr_name, ctx=ast.Load()), node
                )

        # eval('valid_identifier') -> valid_identifier
        if (
            self.ctx.remap_is(node.func.id, ["eval"])
            and self.ctx.is_usable(node.func.id)
            and len(node.args) == 1
            and not node.keywords
            and not isinstance(node.args[0], ast.Starred)
        ):
            ident = self._eval_identifier(node.args[0])
            if ident is not None:
                LOGGER.debug(f"Inlined {node.func.id}({ident!r}) -> {ident}")
                return ast.copy_location(ast.Name(id=ident, ctx=ast.Load()), node)

        # __import__('mod') -> mod (+ ensure import mod at module top)
        if (
            node.func.id == "__import__"
            and self._is_builtin_usable("__import__")
            and len(node.args) == 1
        ):
            mod_name = self._eval_identifier(node.args[0])
            if mod_name is not None:
                existing_entry = self.ctx.get(mod_name)
                if (
                    not self.ctx.is_usable(mod_name)
                    or self.ctx.remap_get(mod_name) is not None
                    or (
                        existing_entry is not None
                        and not isinstance(existing_entry.get(), ImportSymbol)
                    )
                ):
                    return node
                if mod_name not in self._needed_imports:
                    self._needed_imports.append(mod_name)
                LOGGER.debug(f"Inlined __import__({mod_name!r}) -> {mod_name}")
                return ast.copy_location(ast.Name(id=mod_name, ctx=ast.Load()), node)

        return node
