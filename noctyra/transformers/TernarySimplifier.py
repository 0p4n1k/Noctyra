from __future__ import annotations

import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER

_INVERT_CMP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}


def _is_bool_expr(node: ast.AST) -> bool:
    return isinstance(node, (ast.Compare, ast.BoolOp)) or (
        isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)
    )


def _is_pure_expr(node: ast.AST) -> bool:
    if isinstance(node, (ast.Name, ast.Constant)):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_pure_expr(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_pure_expr(node.left) and _is_pure_expr(node.right)
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


class TernarySimplifier(BaseTransformer):
    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if not isinstance(node.op, ast.Not):
            return node

        operand = node.operand
        if (
            isinstance(operand, ast.Compare)
            and len(operand.ops) == 1
            and len(operand.comparators) == 1
        ):
            op_type = type(operand.ops[0])
            inv_cls = _INVERT_CMP.get(op_type)
            if inv_cls is not None:
                LOGGER.debug(
                    f"Inverted negated comparison: {op_type.__name__} -> {inv_cls.__name__}"
                )
                return ast.copy_location(
                    ast.Compare(
                        left=operand.left,
                        ops=[inv_cls()],
                        comparators=operand.comparators,
                    ),
                    node,
                )

        if (
            isinstance(operand, ast.UnaryOp)
            and isinstance(operand.op, ast.Not)
            and _is_bool_expr(operand.operand)
        ):
            LOGGER.debug("Simplified double negation")
            return ast.copy_location(operand.operand, node)

        return node

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        self.generic_visit(node)

        if _is_pure_expr(node.body) and ast.dump(node.body) == ast.dump(node.orelse):
            LOGGER.debug("Simplified identical-branch ternary expression")
            return ast.copy_location(node.body, node)

        if isinstance(node.body, ast.Constant) and isinstance(
            node.orelse, ast.Constant
        ):
            if (
                node.body.value is True
                and node.orelse.value is False
                and _is_bool_expr(node.test)
            ):
                LOGGER.debug("Simplified `True if cond else False`")
                return ast.copy_location(node.test, node)

            if node.body.value is False and node.orelse.value is True:
                LOGGER.debug("Simplified `False if cond else True`")
                return ast.copy_location(
                    ast.UnaryOp(op=ast.Not(), operand=node.test), node
                )

        return node

    def visit_If(self, node: ast.If) -> Any:
        self.generic_visit(node)

        if (
            len(node.body) == 1
            and len(node.orelse) == 1
            and _is_pure_stmt(node.body[0])
            and ast.dump(node.body[0]) == ast.dump(node.orelse[0])
        ):
            LOGGER.debug("Simplified identical-branch if statement")
            return node.body

        return node
