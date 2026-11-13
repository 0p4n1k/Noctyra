from __future__ import annotations

import ast
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


class BasicInliner(BaseTransformer):
    """Inline dynamic lookups: globals/locals/builtins subscripts, getattr, __import__."""

    def __init__(self) -> None:
        super().__init__()
        self._needed_imports: list[str] = []

    def _eval_identifier(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value if node.value.isidentifier() else None
        res = self.eval(node)
        if res is not None:
            val = self.unwrap(res)
            if isinstance(val, str) and val.isidentifier():
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
                node.body = new_imports + list(node.body)
                ast.fix_missing_locations(node)

        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        ident = self._eval_identifier(node.slice)
        if ident is None:
            return node

        # globals()['x'] / locals()['x']
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if (
                self.ctx.remap_is(node.value.func.id, ["globals", "locals"])
                and self.ctx.is_usable(node.value.func.id)
                and not node.value.args
                and not node.value.keywords
            ):
                LOGGER.debug(f"Inlined {node.value.func.id}()[{ident!r}] -> {ident}")
                return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)

        # __builtins__['print']
        if isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
            LOGGER.debug(f"Inlined __builtins__[{ident!r}] -> {ident}")
            return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)

        # builtins.__dict__['print']
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in ("builtins", "__builtins__")
        ):
            LOGGER.debug(f"Inlined builtins.__dict__[{ident!r}] -> {ident}")
            return ast.copy_location(ast.Name(id=ident, ctx=node.ctx), node)

        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name) or node.keywords:
            return node

        # getattr(obj, 'attr') -> obj.attr (or attr if obj is builtins/__builtins__)
        if node.func.id == "getattr" and len(node.args) == 2:
            attr_name = self._eval_identifier(node.args[1])
            if attr_name is not None:
                obj = node.args[0]
                if isinstance(obj, ast.Name) and obj.id in ("builtins", "__builtins__"):
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

        # __import__('mod') -> mod (+ ensure import mod at module top)
        if node.func.id == "__import__" and len(node.args) == 1:
            mod_name = self._eval_identifier(node.args[0])
            if mod_name is not None:
                if mod_name not in self._needed_imports:
                    self._needed_imports.append(mod_name)
                LOGGER.debug(f"Inlined __import__({mod_name!r}) -> {mod_name}")
                return ast.copy_location(ast.Name(id=mod_name, ctx=ast.Load()), node)

        return node
