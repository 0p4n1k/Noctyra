from __future__ import annotations

import ast
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


def _is_int_const(node: ast.AST, value: int) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
        and node.value == value
    )


def _is_pure_expr(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.Name, ast.Constant))
        or (isinstance(node, ast.UnaryOp) and _is_pure_expr(node.operand))
        or (
            isinstance(node, ast.BinOp)
            and _is_pure_expr(node.left)
            and _is_pure_expr(node.right)
        )
    )


def _same_pure_ast(a: ast.AST, b: ast.AST) -> bool:
    return _is_pure_expr(a) and _is_pure_expr(b) and ast.dump(a) == ast.dump(b)


def _match_two_times(node: ast.AST) -> ast.BinOp | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        if _is_int_const(node.left, 2) and isinstance(node.right, ast.BinOp):
            return node.right
        if _is_int_const(node.right, 2) and isinstance(node.left, ast.BinOp):
            return node.left
    return None


class AlgebraicSimplifier(BaseTransformer):
    """Simplify algebraic identities and Mixed Boolean-Arithmetic (MBA) patterns."""

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)

        if (
            isinstance(node.op, ast.Invert)
            and isinstance(node.operand, ast.UnaryOp)
            and isinstance(node.operand.op, ast.Invert)
        ):
            LOGGER.debug("Simplified ~~x -> x")
            return ast.copy_location(node.operand.operand, node)

        if (
            isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.UnaryOp)
            and isinstance(node.operand.op, ast.USub)
        ):
            LOGGER.debug("Simplified --x -> x")
            return ast.copy_location(node.operand.operand, node)

        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        left, right, op = node.left, node.right, node.op

        # Additive / bitwise zero identities
        if isinstance(op, (ast.Add, ast.BitXor, ast.BitOr)):
            if _is_int_const(right, 0):
                return ast.copy_location(left, node)
            if _is_int_const(left, 0):
                return ast.copy_location(right, node)

        if isinstance(op, (ast.Sub, ast.LShift, ast.RShift)) and _is_int_const(
            right, 0
        ):
            return ast.copy_location(left, node)

        # Multiplicative / power / mask identities
        if isinstance(op, ast.Mult):
            if _is_int_const(right, 1):
                return ast.copy_location(left, node)
            if _is_int_const(left, 1):
                return ast.copy_location(right, node)

        if isinstance(op, (ast.FloorDiv, ast.Pow)) and _is_int_const(right, 1):
            return ast.copy_location(left, node)

        if isinstance(op, ast.BitAnd):
            if _is_int_const(right, -1):
                return ast.copy_location(left, node)
            if _is_int_const(left, -1):
                return ast.copy_location(right, node)

        # MBA: (x ^ y) + 2 * (x & y) -> x + y
        if isinstance(op, ast.Add):
            for xor_cand, mul_cand in ((left, right), (right, left)):
                if isinstance(xor_cand, ast.BinOp) and isinstance(
                    xor_cand.op, ast.BitXor
                ):
                    and_node = _match_two_times(mul_cand)
                    if and_node is not None and isinstance(and_node.op, ast.BitAnd):
                        if (
                            _same_pure_ast(xor_cand.left, and_node.left)
                            and _same_pure_ast(xor_cand.right, and_node.right)
                        ) or (
                            _same_pure_ast(xor_cand.left, and_node.right)
                            and _same_pure_ast(xor_cand.right, and_node.left)
                        ):
                            LOGGER.debug(
                                "Simplified MBA (x ^ y) + 2 * (x & y) -> x + y"
                            )
                            return ast.copy_location(
                                ast.BinOp(
                                    left=xor_cand.left,
                                    op=ast.Add(),
                                    right=xor_cand.right,
                                ),
                                node,
                            )

            # MBA: (x | y) + (x & y) -> x + y
            for or_cand, and_cand in ((left, right), (right, left)):
                if (
                    isinstance(or_cand, ast.BinOp)
                    and isinstance(or_cand.op, ast.BitOr)
                    and isinstance(and_cand, ast.BinOp)
                    and isinstance(and_cand.op, ast.BitAnd)
                ):
                    if (
                        _same_pure_ast(or_cand.left, and_cand.left)
                        and _same_pure_ast(or_cand.right, and_cand.right)
                    ) or (
                        _same_pure_ast(or_cand.left, and_cand.right)
                        and _same_pure_ast(or_cand.right, and_cand.left)
                    ):
                        LOGGER.debug("Simplified MBA (x | y) + (x & y) -> x + y")
                        return ast.copy_location(
                            ast.BinOp(
                                left=or_cand.left, op=ast.Add(), right=or_cand.right
                            ),
                            node,
                        )

        # MBA: (x | y) - (x ^ y) -> x & y
        if (
            isinstance(op, ast.Sub)
            and isinstance(left, ast.BinOp)
            and isinstance(left.op, ast.BitOr)
            and isinstance(right, ast.BinOp)
            and isinstance(right.op, ast.BitXor)
        ):
            if (
                _same_pure_ast(left.left, right.left)
                and _same_pure_ast(left.right, right.right)
            ) or (
                _same_pure_ast(left.left, right.right)
                and _same_pure_ast(left.right, right.left)
            ):
                LOGGER.debug("Simplified MBA (x | y) - (x ^ y) -> x & y")
                return ast.copy_location(
                    ast.BinOp(left=left.left, op=ast.BitAnd(), right=left.right), node
                )

        # MBA: (x ^ y) | (x & y) -> x | y
        if isinstance(op, ast.BitOr):
            for xor_cand, and_cand in ((left, right), (right, left)):
                if (
                    isinstance(xor_cand, ast.BinOp)
                    and isinstance(xor_cand.op, ast.BitXor)
                    and isinstance(and_cand, ast.BinOp)
                    and isinstance(and_cand.op, ast.BitAnd)
                ):
                    if (
                        _same_pure_ast(xor_cand.left, and_cand.left)
                        and _same_pure_ast(xor_cand.right, and_cand.right)
                    ) or (
                        _same_pure_ast(xor_cand.left, and_cand.right)
                        and _same_pure_ast(xor_cand.right, and_cand.left)
                    ):
                        LOGGER.debug("Simplified MBA (x ^ y) | (x & y) -> x | y")
                        return ast.copy_location(
                            ast.BinOp(
                                left=xor_cand.left, op=ast.BitOr(), right=xor_cand.right
                            ),
                            node,
                        )

        return node
