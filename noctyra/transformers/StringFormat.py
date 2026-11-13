from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
from typing import Any
import ast
import re
import string


class StringFormatTransformer(BaseTransformer):
    """Safely fold constant str.format(), %-formatting, and bytes/bytearray.decode()."""

    def _max_alloc(self) -> int:
        return getattr(self, "max_allocation", 100_000)

    def _eval_bytes_like(self, node: ast.AST) -> bytes | bytearray | None:
        max_alloc = self._max_alloc()
        res = self.eval(node)
        if res is not None:
            val = self.unwrap(res)
            if isinstance(val, (bytes, bytearray)) and len(val) <= max_alloc:
                return val
            return None

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("bytearray", "bytes")
        ):
            cls: type[bytes] | type[bytearray] = (
                bytearray if node.func.id == "bytearray" else bytes
            )
            call_args: list[Any] = []
            for arg in node.args:
                if isinstance(arg, ast.Starred):
                    s_res = self.eval(arg.value)
                    if s_res is None:
                        return None
                    s_val = self.unwrap(s_res)
                    if not isinstance(s_val, (list, tuple)) or len(s_val) > max_alloc:
                        return None
                    call_args.extend(s_val)
                else:
                    a_res = self.eval(arg)
                    if a_res is not None:
                        a_val: Any = self.unwrap(a_res)
                    else:
                        a_val = self._eval_bytes_like(arg)
                        if a_val is None:
                            return None
                    call_args.append(a_val)

            call_kwargs: dict[str, Any] = {}
            for kw in node.keywords:
                kw_res = self.eval(kw.value)
                if kw_res is None:
                    return None
                kw_val = self.unwrap(kw_res)
                if kw.arg is None:
                    if not isinstance(kw_val, dict) or not all(
                        isinstance(k, str) for k in kw_val
                    ):
                        return None
                    call_kwargs.update(kw_val)
                else:
                    call_kwargs[kw.arg] = kw_val

            if len(call_args) == 1 and not call_kwargs:
                first = call_args[0]
                if isinstance(first, int) and not isinstance(first, bool):
                    if first < 0 or first > max_alloc:
                        return None
                elif isinstance(first, (list, tuple, bytes, bytearray, str)):
                    if len(first) > max_alloc:
                        return None

            try:
                out = cls(*call_args, **call_kwargs)
            except Exception:
                return None

            if len(out) <= max_alloc:
                return out

        return None

    def _fold_str_format(self, node: ast.Call) -> ast.AST | None:
        if not isinstance(node.func, ast.Attribute):
            return None

        recv_res = self.eval(node.func.value)
        if recv_res is None:
            return None

        recv = self.unwrap(recv_res)
        if not isinstance(recv, str):
            return None

        max_alloc = self._max_alloc()
        if len(recv) > max_alloc:
            return None

        pos_args: list[Any] = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                s_res = self.eval(arg.value)
                if s_res is None:
                    return None
                s_val = self.unwrap(s_res)
                if not isinstance(s_val, (list, tuple)) or len(s_val) > max_alloc:
                    return None
                pos_args.extend(s_val)
            else:
                arg_res = self.eval(arg)
                if arg_res is None:
                    return None
                pos_args.append(self.unwrap(arg_res))

        kw_args: dict[str, Any] = {}
        for kw in node.keywords:
            kw_res = self.eval(kw.value)
            if kw_res is None:
                return None
            kw_val = self.unwrap(kw_res)
            if kw.arg is None:
                if (
                    not isinstance(kw_val, dict)
                    or len(kw_val) > max_alloc
                    or not all(isinstance(k, str) for k in kw_val)
                ):
                    return None
                kw_args.update(kw_val)
            else:
                kw_args[kw.arg] = kw_val

        has_nested = False
        try:
            for _, _, format_spec, _ in string.Formatter().parse(recv):
                if format_spec:
                    if "{" in format_spec:
                        has_nested = True
                    for num_str in re.findall(r"\d+", format_spec):
                        if int(num_str) > max_alloc:
                            return None
        except Exception:
            return None

        if has_nested:
            for val in (*pos_args, *kw_args.values()):
                if (
                    isinstance(val, int)
                    and not isinstance(val, bool)
                    and abs(val) > max_alloc
                ):
                    return None

        try:
            res = recv.format(*pos_args, **kw_args)
        except Exception:
            return None

        if isinstance(res, str) and len(res) <= max_alloc:
            LOGGER.debug(f"Folded str.format into constant: {res!r}")
            return ast.copy_location(ast.Constant(value=res), node)

        return None

    def _fold_decode(self, node: ast.Call) -> ast.AST | None:
        if not isinstance(node.func, ast.Attribute):
            return None

        recv_bytes = self._eval_bytes_like(node.func.value)
        if recv_bytes is None:
            return None

        dec_args: list[Any] = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                s_res = self.eval(arg.value)
                if s_res is None:
                    return None
                s_val = self.unwrap(s_res)
                if not isinstance(s_val, (list, tuple)):
                    return None
                dec_args.extend(s_val)
            else:
                arg_res = self.eval(arg)
                if arg_res is None:
                    return None
                dec_args.append(self.unwrap(arg_res))

        dec_kwargs: dict[str, Any] = {}
        for kw in node.keywords:
            kw_res = self.eval(kw.value)
            if kw_res is None:
                return None
            kw_val = self.unwrap(kw_res)
            if kw.arg is None:
                if not isinstance(kw_val, dict) or not all(
                    isinstance(k, str) for k in kw_val
                ):
                    return None
                dec_kwargs.update(kw_val)
            else:
                dec_kwargs[kw.arg] = kw_val

        try:
            res = recv_bytes.decode(*dec_args, **dec_kwargs)
        except Exception:
            return None

        if isinstance(res, str) and len(res) <= self._max_alloc():
            LOGGER.debug(f"Folded decode into constant: {res!r}")
            return ast.copy_location(ast.Constant(value=res), node)

        return None

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "format":
                folded = self._fold_str_format(node)
                if folded is not None:
                    return folded
            elif node.func.attr == "decode":
                folded = self._fold_decode(node)
                if folded is not None:
                    return folded

        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if not isinstance(node.op, ast.Mod):
            return node

        left_res = self.eval(node.left)
        if left_res is None:
            return node

        left = self.unwrap(left_res)
        if not isinstance(left, (str, bytes)):
            return node

        max_alloc = self._max_alloc()
        if len(left) > max_alloc:
            return node

        right_res = self.eval(node.right)
        if right_res is None:
            return node

        right = self.unwrap(right_res)

        if isinstance(left, str):
            for num_str in re.findall(r"%\s*[-+#0 ]*(\d+)", left):
                if int(num_str) > max_alloc:
                    return node
            if "*" in left and isinstance(right, tuple):
                for item in right:
                    if (
                        isinstance(item, int)
                        and not isinstance(item, bool)
                        and abs(item) > max_alloc
                    ):
                        return node
        else:
            for num_bytes in re.findall(rb"%\s*[-+#0 ]*(\d+)", left):
                if int(num_bytes) > max_alloc:
                    return node
            if b"*" in left and isinstance(right, tuple):
                for item in right:
                    if (
                        isinstance(item, int)
                        and not isinstance(item, bool)
                        and abs(item) > max_alloc
                    ):
                        return node

        try:
            res = left % right
        except Exception:
            return node

        if isinstance(res, (str, bytes)) and len(res) <= max_alloc:
            LOGGER.debug(f"Folded %-format into constant: {res!r}")
            return ast.copy_location(ast.Constant(value=res), node)

        return node
