from __future__ import annotations

import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


class ExecUnpacker(BaseTransformer):
    """Unpack static ``eval(...)`` and ``exec(compile(...))`` calls."""

    def _eval_value(self, node: ast.AST) -> Any:
        res = self.eval(node)
        if res is None:
            return None
        return self.unwrap(res)

    def _extract_compile_code(
        self,
        node: ast.AST,
        expected_mode: str,
        allow_bytes: bool = False,
    ) -> str | None:
        if not isinstance(node, ast.Call):
            return None
        if not isinstance(node.func, ast.Name) or node.func.id != "compile":
            return None
        if len(node.args) < 3 or node.keywords:
            return None

        mode = self._eval_value(node.args[2])
        if mode != expected_mode:
            return None

        raw_code = self._eval_value(node.args[0])
        if isinstance(raw_code, bytes) and allow_bytes:
            if len(raw_code) > self.max_allocation:
                return None
            try:
                code = raw_code.decode("utf-8")
            except UnicodeDecodeError:
                return None
        elif isinstance(raw_code, str):
            code = raw_code
        else:
            return None

        if len(code) > self.max_allocation:
            return None
        return code

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name) or node.func.id != "eval":
            return node
        if len(node.args) != 1 or node.keywords:
            return node

        arg = node.args[0]
        code = self._extract_compile_code(arg, expected_mode="eval")
        if code is None:
            val = self._eval_value(arg)
            if not isinstance(val, str) or len(val) > self.max_allocation:
                return node
            code = val

        try:
            parsed = ast.parse(code, mode="eval").body
        except SyntaxError:
            LOGGER.debug("ExecUnpacker: SyntaxError while parsing eval() payload")
            return node

        ast.copy_location(parsed, node)
        return parsed

    def visit_Expr(self, node: ast.Expr) -> Any:
        self.generic_visit(node)

        call = node.value
        if not isinstance(call, ast.Call):
            return node
        if not isinstance(call.func, ast.Name) or call.func.id != "exec":
            return node
        if len(call.args) != 1 or call.keywords:
            return node

        code = self._extract_compile_code(
            call.args[0],
            expected_mode="exec",
            allow_bytes=True,
        )
        if code is None:
            return node

        try:
            stmts = ast.parse(code).body
        except SyntaxError:
            LOGGER.debug("ExecUnpacker: SyntaxError while parsing exec() payload")
            return node

        for stmt in stmts:
            ast.copy_location(stmt, node)

        return stmts
