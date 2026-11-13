from __future__ import annotations

import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _strip_redundant_pass(stmts: list[ast.stmt]) -> list[ast.stmt]:
    if len(stmts) <= 1:
        return stmts
    non_pass = [stmt for stmt in stmts if not isinstance(stmt, ast.Pass)]
    if non_pass:
        return non_pass
    return [stmts[0]]


def _contains_break_or_continue(stmts: list[ast.stmt]) -> bool:
    for stmt in stmts:
        for child in ast.walk(stmt):
            if isinstance(child, (ast.Break, ast.Continue)):
                return True
    return False


def _is_pure_expr(node: ast.AST) -> bool:
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_pure_expr(node.operand)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            return False
        return _is_pure_expr(node.left) and _is_pure_expr(node.right)
    if isinstance(node, ast.BoolOp):
        return all(_is_pure_expr(v) for v in node.values)
    if isinstance(node, ast.Compare):
        return _is_pure_expr(node.left) and all(
            _is_pure_expr(c) for c in node.comparators
        )
    if isinstance(node, ast.IfExp):
        return (
            _is_pure_expr(node.test)
            and _is_pure_expr(node.body)
            and _is_pure_expr(node.orelse)
        )
    if isinstance(node, ast.JoinedStr):
        return all(
            isinstance(v, ast.Constant)
            or (
                isinstance(v, ast.FormattedValue)
                and _is_pure_expr(v.value)
                and (v.format_spec is None or _is_pure_expr(v.format_spec))
            )
            for v in node.values
        )
    return False


def _is_pure_stmt(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr):
        return _is_pure_expr(stmt.value)
    if isinstance(stmt, ast.Assign):
        return all(isinstance(t, ast.Name) for t in stmt.targets) and _is_pure_expr(
            stmt.value
        )
    return False


class ControlFlowSimplifier(BaseTransformer):
    def visit_Assign(self, node: ast.Assign) -> Any:
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Name)
            and node.targets[0].id == node.value.id
        ):
            LOGGER.debug(
                f"Removed self-assignment: {node.targets[0].id} = {node.value.id}"
            )
            return None
        return super().visit_Assign(node)

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        res = super().visit_FunctionDef(node)
        if isinstance(res, ast.FunctionDef):
            res.body = _strip_redundant_pass(res.body)
        return res

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        res = super().visit_AsyncFunctionDef(node)
        if isinstance(res, ast.AsyncFunctionDef):
            res.body = _strip_redundant_pass(res.body)
        return res

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        res = super().visit_ClassDef(node)
        if isinstance(res, ast.ClassDef):
            res.body = _strip_redundant_pass(res.body)
        return res

    def visit_If(self, node: ast.If) -> ast.If:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        return node

    def visit_For(self, node: ast.For) -> ast.For:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AsyncFor:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        return node

    def visit_With(self, node: ast.With) -> ast.With:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        return node

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AsyncWith:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        return node

    def visit_While(self, node: ast.While) -> Any:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)

        test_res = self.eval(node.test)
        if (
            test_res is not None
            and bool(self.unwrap(test_res))
            and not node.orelse
            and node.body
            and isinstance(node.body[-1], ast.Break)
            and not _contains_break_or_continue(node.body[:-1])
        ):
            LOGGER.debug("Unwrapped single-iteration while loop")
            return node.body[:-1]

        return node

    def visit_Try(self, node: ast.Try) -> Any:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        node.finalbody = _strip_redundant_pass(node.finalbody)

        if not node.finalbody and all(_is_pure_stmt(stmt) for stmt in node.body):
            LOGGER.debug("Unwrapped pure try block")
            return [*node.body, *node.orelse]

        return node
