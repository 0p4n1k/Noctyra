from __future__ import annotations

import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _is_pure_expr(expr: ast.AST, *, allow_containers: bool = True) -> bool:
    if isinstance(expr, (ast.Constant, ast.Name, ast.Lambda)):
        return True
    if isinstance(expr, ast.Attribute):
        return _is_pure_expr(expr.value, allow_containers=allow_containers)
    if isinstance(expr, ast.Subscript):
        return _is_pure_expr(
            expr.value, allow_containers=allow_containers
        ) and _is_pure_expr(expr.slice, allow_containers=allow_containers)
    if isinstance(expr, ast.Slice):
        return all(
            part is None or _is_pure_expr(part, allow_containers=allow_containers)
            for part in (expr.lower, expr.upper, expr.step)
        )
    if isinstance(expr, ast.UnaryOp):
        return _is_pure_expr(expr.operand, allow_containers=allow_containers)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        return _is_pure_expr(
            expr.left, allow_containers=allow_containers
        ) and _is_pure_expr(expr.right, allow_containers=allow_containers)
    if allow_containers and isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return not any(isinstance(e, ast.Starred) for e in expr.elts) and all(
            _is_pure_expr(e, allow_containers=True) for e in expr.elts
        )
    if allow_containers and isinstance(expr, ast.Dict):
        return all(
            k is not None
            and _is_pure_expr(k, allow_containers=True)
            and _is_pure_expr(v, allow_containers=True)
            for k, v in zip(expr.keys, expr.values)
        )
    return False


def _hoist_expr(expr: ast.expr) -> list[ast.stmt]:
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)) and not any(
        isinstance(e, ast.Starred) for e in expr.elts
    ):
        stmts: list[ast.stmt] = []
        for elt in expr.elts:
            stmts.extend(_hoist_expr(elt))
        return stmts
    if _is_pure_expr(expr, allow_containers=True):
        return []
    return [ast.copy_location(ast.Expr(value=expr), expr)]


def _has_future_annotations(module: ast.Module) -> bool:
    for stmt in module.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
            if any(alias.name == "annotations" for alias in stmt.names):
                return True
    return False


class AnnotationTransformer(BaseTransformer):
    """Hoist runtime annotation side effects and strip dead local annotations."""

    def __init__(self) -> None:
        super().__init__()
        self._scope_stack: list[str] = ["module"]

    def visit_Module(self, node: ast.Module) -> ast.Module:
        if _has_future_annotations(node):
            return node
        self._scope_stack = ["module"]
        node.body = self._visit_stmt_list(node.body)
        ast.fix_missing_locations(node)
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

    def _ensure_non_empty(self, stmts: list[ast.stmt], ref: ast.AST) -> list[ast.stmt]:
        if not stmts:
            return [ast.copy_location(ast.Pass(), ref)]
        return stmts

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        scope = self._scope_stack[-1]

        if scope == "function":
            if node.value is not None:
                LOGGER.debug("Stripping dead local AnnAssign annotation")
                return ast.copy_location(
                    ast.Assign(targets=[node.target], value=node.value), node
                )
            if isinstance(node.target, ast.Name) or _is_pure_expr(node.target):
                LOGGER.debug("Removing dead local AnnAssign without value")
                return None
            return node

        # Module or class scope: annotation is evaluated at runtime AFTER value assignment
        if node.value is not None:
            assign = ast.copy_location(
                ast.Assign(targets=[node.target], value=node.value), node
            )
            if _is_pure_expr(node.annotation, allow_containers=True):
                return assign
            hoisted = _hoist_expr(node.annotation)
            LOGGER.debug(f"Hoisting {len(hoisted)} statement(s) from AnnAssign")
            return [assign, *hoisted]

        if _is_pure_expr(node.annotation, allow_containers=True):
            return node
        if isinstance(node.target, ast.Name) or _is_pure_expr(node.target):
            hoisted = _hoist_expr(node.annotation)
            LOGGER.debug(
                f"Hoisting {len(hoisted)} statement(s) from valueless AnnAssign"
            )
            return hoisted
        return node

    def _visit_func_def(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Any:
        can_hoist = (
            all(_is_pure_expr(d) for d in node.decorator_list)
            and all(_is_pure_expr(d) for d in node.args.defaults)
            and all(d is None or _is_pure_expr(d) for d in node.args.kw_defaults)
        )

        hoisted: list[ast.stmt] = []
        if can_hoist:
            ordered_args: list[ast.arg] = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + ([node.args.vararg] if node.args.vararg is not None else [])
                + list(node.args.kwonlyargs)
                + ([node.args.kwarg] if node.args.kwarg is not None else [])
            )
            for arg in ordered_args:
                if arg.annotation is not None and not _is_pure_expr(
                    arg.annotation, allow_containers=True
                ):
                    hoisted.extend(_hoist_expr(arg.annotation))
                    arg.annotation = None
            if node.returns is not None and not _is_pure_expr(
                node.returns, allow_containers=True
            ):
                hoisted.extend(_hoist_expr(node.returns))
                node.returns = None

        self._scope_stack.append("function")
        node.body = self._ensure_non_empty(self._visit_stmt_list(node.body), node)
        self._scope_stack.pop()

        if hoisted:
            LOGGER.debug(
                f"Hoisted {len(hoisted)} annotation statement(s) before {node.name}"
            )
            return [*hoisted, node]
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        return self._visit_func_def(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        return self._visit_func_def(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._scope_stack.append("class")
        node.body = self._ensure_non_empty(self._visit_stmt_list(node.body), node)
        self._scope_stack.pop()
        return node

    def visit_If(self, node: ast.If) -> Any:
        node.body = self._ensure_non_empty(self._visit_stmt_list(node.body), node)
        if node.orelse:
            node.orelse = self._visit_stmt_list(node.orelse)
        return node

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> Any:
        node.body = self._ensure_non_empty(self._visit_stmt_list(node.body), node)
        if node.orelse:
            node.orelse = self._visit_stmt_list(node.orelse)
        return node

    def visit_For(self, node: ast.For) -> Any:
        return self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> Any:
        return self._visit_loop(node)

    def visit_While(self, node: ast.While) -> Any:
        return self._visit_loop(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> Any:
        node.body = self._ensure_non_empty(self._visit_stmt_list(node.body), node)
        return node

    def visit_With(self, node: ast.With) -> Any:
        return self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        return self._visit_with(node)

    def visit_Try(self, node: ast.Try | Any) -> Any:
        node.body = self._ensure_non_empty(self._visit_stmt_list(node.body), node)
        for handler in node.handlers:
            handler.body = self._ensure_non_empty(
                self._visit_stmt_list(handler.body), handler
            )
        if node.orelse:
            node.orelse = self._visit_stmt_list(node.orelse)
        if node.finalbody:
            node.finalbody = self._visit_stmt_list(node.finalbody)
        return node

    def visit_TryStar(self, node: Any) -> Any:
        return self.visit_Try(node)

    def visit_Match(self, node: Any) -> Any:
        node.subject = self.visit(node.subject)
        for case in node.cases:
            if case.guard is not None:
                case.guard = self.visit(case.guard)
            ref = case if hasattr(case, "lineno") else node
            case.body = self._ensure_non_empty(self._visit_stmt_list(case.body), ref)
        return node
