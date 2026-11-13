from __future__ import annotations

import ast
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _is_pure_rhs(node: ast.AST) -> bool:
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_pure_rhs(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_pure_rhs(node.left) and _is_pure_rhs(node.right)
    if isinstance(node, ast.BoolOp):
        return all(_is_pure_rhs(v) for v in node.values)
    if isinstance(node, ast.Compare):
        return _is_pure_rhs(node.left) and all(
            _is_pure_rhs(c) for c in node.comparators
        )
    if isinstance(node, ast.IfExp):
        return (
            _is_pure_rhs(node.test)
            and _is_pure_rhs(node.body)
            and _is_pure_rhs(node.orelse)
        )
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_pure_rhs(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (k is None or _is_pure_rhs(k)) and _is_pure_rhs(v)
            for k, v in zip(node.keys, node.values)
        )
    if isinstance(node, ast.JoinedStr):
        return all(
            isinstance(v, ast.Constant)
            or (isinstance(v, ast.FormattedValue) and _is_pure_rhs(v.value))
            for v in node.values
        )
    return False


def _collect_loaded_names(node: ast.AST) -> set[str]:
    loaded: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            loaded.add(child.id)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            loaded.update(child.names)
    return loaded


def _collect_used_names_in_func(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    used: set[str] = set()
    for stmt in node.body:
        used.update(_collect_loaded_names(stmt))
    return used


class DeadCodeRemover(BaseTransformer):
    active = True

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self.generic_visit(node)

        # Collect all loaded/referenced names outside of import statements
        used_names: set[str] = set()
        for stmt in node.body:
            if not isinstance(stmt, (ast.Import, ast.ImportFrom)):
                used_names.update(_collect_loaded_names(stmt))

        new_body: list[ast.stmt] = []
        for stmt in node.body:
            if isinstance(stmt, ast.Import):
                kept_aliases = [
                    alias
                    for alias in stmt.names
                    if (alias.asname or alias.name.split(".")[0]) in used_names
                ]
                if not kept_aliases:
                    LOGGER.debug(f"Removed unused import: {ast.unparse(stmt)}")
                    continue
                stmt.names = kept_aliases
            elif isinstance(stmt, ast.ImportFrom):
                if any(alias.name == "*" for alias in stmt.names):
                    new_body.append(stmt)
                    continue
                kept_aliases = [
                    alias
                    for alias in stmt.names
                    if (alias.asname or alias.name) in used_names
                ]
                if not kept_aliases:
                    LOGGER.debug(f"Removed unused from-import: {ast.unparse(stmt)}")
                    continue
                stmt.names = kept_aliases
            new_body.append(stmt)

        node.body = new_body
        return node

    def visit_If(self, node: ast.If):
        self.generic_visit(node)

        test_res = self.eval(node.test)
        if test_res is None:
            return node

        test_value = self.unwrap(test_res)
        if bool(test_value):
            return node.body
        return node.orelse

    def visit_While(self, node: ast.While):
        self.generic_visit(node)

        test_res = self.eval(node.test)
        if test_res is not None and not bool(self.unwrap(test_res)):
            LOGGER.debug("Removed dead while loop")
            return node.orelse

        return node

    def _clean_func_body(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        self.generic_visit(node)

        truncated: list[ast.stmt] = []
        for stmt in node.body:
            truncated.append(stmt)
            if isinstance(stmt, (ast.Return, ast.Raise)):
                break
        node.body = truncated

        used_names = _collect_used_names_in_func(node)
        cleaned: list[ast.stmt] = []
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id not in used_names
                and _is_pure_rhs(stmt.value)
            ):
                LOGGER.debug(f"Removed dead local assignment: {stmt.targets[0].id}")
                continue
            cleaned.append(stmt)

        if not cleaned:
            cleaned = [ast.Pass()]

        node.body = cleaned
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        return self._clean_func_body(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self._clean_func_body(node)
