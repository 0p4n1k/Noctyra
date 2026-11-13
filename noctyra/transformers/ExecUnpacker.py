from __future__ import annotations

import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER


class ExecUnpacker(BaseTransformer):
    """Unpack static ``eval(...)`` and ``exec(...)`` calls."""

    def __init__(self) -> None:
        super().__init__()
        self._class_setters: dict[tuple[str, str], tuple[list[str], int, int]] = {}
        self._class_getters: dict[tuple[str, str], list[str]] = {}
        self._globals_store: dict[str, bytes | str] = {}

    def _eval_value(self, node: ast.AST) -> Any:
        res = self.eval(node)
        if res is None:
            return None
        return self.unwrap(res)

    def _is_globals_call(self, node: ast.AST, extra_names: set[str] | None = None) -> bool:
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and not node.args
            and not node.keywords
        ):
            return False
        if self.ctx.remap_is(node.func.id, ["globals"]):
            return True
        if extra_names and node.func.id in extra_names:
            return True
        return False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or not item.body:
                continue
            arg_names = [a.arg for a in item.args.args]
            # Check for setter: g()[key_arg] = val_arg
            first = item.body[0]
            if (
                isinstance(first, ast.Assign)
                and len(first.targets) == 1
                and isinstance(first.targets[0], ast.Subscript)
                and isinstance(first.targets[0].slice, ast.Name)
                and isinstance(first.value, ast.Name)
            ):
                g_names = {
                    a.arg
                    for a, d in zip(
                        reversed(item.args.args), reversed(item.args.defaults)
                    )
                    if isinstance(d, ast.Name) and self.ctx.remap_is(d.id, ["globals"])
                }
                if self._is_globals_call(first.targets[0].value, g_names):
                    k_name = first.targets[0].slice.id
                    v_name = first.value.id
                    if k_name in arg_names and v_name in arg_names:
                        self._class_setters[(node.name, item.name)] = (
                            arg_names,
                            arg_names.index(k_name),
                            arg_names.index(v_name),
                        )
            # Check for getter: return globals()[key_arg]
            if (
                len(item.body) == 1
                and isinstance(item.body[0], ast.Return)
                and isinstance(item.body[0].value, ast.Subscript)
                and isinstance(item.body[0].value.slice, ast.Name)
                and self._is_globals_call(item.body[0].value.value)
            ):
                k_name = item.body[0].value.slice.id
                if k_name in arg_names:
                    self._class_getters[(node.name, item.name)] = arg_names

        return super().visit_ClassDef(node)

    def _resolve_kw_or_pos(
        self, call: ast.Call, arg_names: list[str], idx: int
    ) -> ast.AST | None:
        if idx < len(call.args):
            return call.args[idx]
        target_name = arg_names[idx]
        for kw in call.keywords:
            if kw.arg == target_name:
                return kw.value
        return None

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

        source_node: ast.AST | None = node.args[0] if len(node.args) >= 1 else None
        mode_node: ast.AST | None = node.args[2] if len(node.args) >= 3 else None
        for kw in node.keywords:
            if kw.arg == "source" and source_node is None:
                source_node = kw.value
            elif kw.arg == "mode" and mode_node is None:
                mode_node = kw.value
            elif kw.arg not in ("source", "filename", "mode"):
                return None

        if source_node is None or mode_node is None:
            return None

        mode = self._eval_value(mode_node)
        if mode != expected_mode:
            return None

        raw_code = self._eval_value(source_node)
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

        # Record / resolve class-based globals()[key] = payload helpers
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        ):
            key_pair = (node.func.value.id, node.func.attr)
            if key_pair in self._class_setters:
                arg_names, k_idx, v_idx = self._class_setters[key_pair]
                k_node = self._resolve_kw_or_pos(node, arg_names, k_idx)
                v_node = self._resolve_kw_or_pos(node, arg_names, v_idx)
                if k_node is not None and v_node is not None:
                    k_val = self._eval_value(k_node)
                    v_val = self._eval_value(v_node)
                    if (
                        isinstance(k_val, str)
                        and isinstance(v_val, (bytes, str))
                        and len(v_val) <= self.max_allocation
                    ):
                        self._globals_store[k_val] = v_val
                return node

            if key_pair in self._class_getters:
                arg_names = self._class_getters[key_pair]
                k_node = self._resolve_kw_or_pos(node, arg_names, 0)
                if k_node is not None:
                    k_val = self._eval_value(k_node)
                    if isinstance(k_val, str) and k_val in self._globals_store:
                        return ast.copy_location(
                            ast.Constant(value=self._globals_store[k_val]), node
                        )
                return node

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

    def _is_exec_call(self, call: ast.Call) -> bool:
        if isinstance(call.func, ast.Name) and call.func.id == "exec":
            return True
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in ("builtins", "__builtins__")
            and call.func.attr == "exec"
        ):
            return True
        return False

    def visit_Expr(self, node: ast.Expr) -> Any:
        self.generic_visit(node)

        call = node.value
        if not isinstance(call, ast.Call):
            return node
        if not self._is_exec_call(call):
            return node
        if len(call.args) not in (1, 2) or call.keywords:
            return node

        code = self._extract_compile_code(
            call.args[0],
            expected_mode="exec",
            allow_bytes=True,
        )
        if code is None:
            val = self._eval_value(call.args[0])
            if isinstance(val, bytes) and len(val) <= self.max_allocation:
                try:
                    code = val.decode("utf-8")
                except UnicodeDecodeError:
                    return node
            elif isinstance(val, str) and len(val) <= self.max_allocation:
                code = val
            else:
                return node

        try:
            stmts = ast.parse(code).body
        except SyntaxError:
            LOGGER.debug("ExecUnpacker: SyntaxError while parsing exec() payload")
            return node

        for stmt in stmts:
            ast.copy_location(stmt, node)

        return stmts
