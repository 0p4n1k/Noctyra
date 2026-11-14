from noctyra.core import (
    Context,
    ImportSymbol,
    LambdaType,
    NoneValue,
    SymbolicValue,
    Variable,
    is_symbolic_ref,
    supported_types,
    unwrap as core_unwrap,
)
from noctyra.utils import ATTR, BIN_OPS, UNARY_OPS, COMP_OPS, FUNCS, WHITELIST, LOGGER
from noctyra.utils.Shared import is_pure_expr
from typing import Any
import ast
import blosc
import brotli
import builtins
import bz2
import lzma
import operator
import re
import struct
import zlib

_UNBOUND_ARG = object()


def _is_pure_eval_arg(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return _is_pure_eval_arg(node.value)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(
            not isinstance(e, ast.Starred) and _is_pure_eval_arg(e)
            for e in node.elts
        )
    if isinstance(node, ast.Dict):
        return all(
            (k is None or _is_pure_eval_arg(k)) and _is_pure_eval_arg(v)
            for k, v in zip(node.keys, node.values)
        )
    return is_pure_expr(node, allow_containers=True)

_stdlib_zstd: Any
try:
    from compression import zstd as _stdlib_zstd_mod  # type: ignore[import-not-found]

    _stdlib_zstd = _stdlib_zstd_mod
except ImportError:
    _stdlib_zstd = None


def _is_zstd_single_frame_bounded(raw_z: bytes, max_allocation: int) -> bool:
    """Validate that raw_z is a single standard zstd frame with declared size <= max_allocation."""
    if len(raw_z) < 6 or raw_z[:4] != b"\x28\xb5\x2f\xfd":
        return False
    fhd = raw_z[4]
    fcs_flag = (fhd >> 6) & 0x3
    single_seg = (fhd >> 5) & 0x1
    has_checksum = (fhd >> 2) & 0x1
    did_len = (0, 1, 2, 4)[fhd & 0x3]
    win_len = 0 if single_seg else 1
    fcs_off = 5 + win_len + did_len
    fcs_size = (1 if single_seg else 0, 2, 4, 8)[fcs_flag]
    if fcs_size == 0 or len(raw_z) < fcs_off + fcs_size:
        return False

    if fcs_size == 1:
        fcs = raw_z[fcs_off]
    elif fcs_size == 2:
        fcs = struct.unpack_from("<H", raw_z, fcs_off)[0] + 256
    elif fcs_size == 4:
        fcs = struct.unpack_from("<I", raw_z, fcs_off)[0]
    else:
        fcs = struct.unpack_from("<Q", raw_z, fcs_off)[0]
    if fcs > max_allocation:
        return False

    pos = fcs_off + fcs_size
    while True:
        if pos + 3 > len(raw_z):
            return False
        bh = int.from_bytes(raw_z[pos : pos + 3], "little")
        last_block = bh & 1
        block_type = (bh >> 1) & 3
        block_size = bh >> 3
        if block_type == 3:
            return False
        pos += 3 + (1 if block_type == 1 else block_size)
        if pos > len(raw_z):
            return False
        if last_block:
            break
    pos += 4 if has_checksum else 0
    return pos == len(raw_z)


class SafeEval(ast.NodeVisitor):
    def __init__(
        self,
        ctx: Context | None = None,
        depth: int = 0,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ) -> None:
        self.depth = depth
        self.max_depth = max_depth
        self.max_allocation = max_allocation
        self.ctx = ctx or Context()

    def _is_builtin_usable(self, name: str) -> bool:
        return (
            self.ctx.is_usable(name)
            and not self.ctx.has(name)
            and self.ctx.remap_get(name) is None
        )

    def exec_custom_func(
        self,
        fn: LambdaType,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ):
        if self.depth >= self.max_depth:
            return None

        if args is None:
            args = []

        if kwargs is None:
            kwargs = {}

        fn_args = fn.get_args()

        posonly_names = [a.arg for a in fn_args.posonlyargs]
        regular_names = [a.arg for a in fn_args.args]
        kwonly_names = [a.arg for a in fn_args.kwonlyargs]
        all_pos = posonly_names + regular_names

        bound: dict[str, Any] = {}
        for i, arg in enumerate(args[: len(all_pos)]):
            bound[all_pos[i]] = arg

        if len(args) > len(all_pos):
            if fn_args.vararg is None:
                return None
            bound[fn_args.vararg.arg] = tuple(args[len(all_pos) :])
        elif fn_args.vararg is not None:
            bound[fn_args.vararg.arg] = ()

        extra_kwargs: dict[str, Any] = {}
        for name, val in kwargs.items():
            if name in regular_names or name in kwonly_names:
                if name in bound:
                    return None
                bound[name] = val
            elif fn_args.kwarg is None:
                return None
            else:
                extra_kwargs[name] = val

        if fn_args.kwarg is not None:
            bound[fn_args.kwarg.arg] = extra_kwargs

        default_start = len(all_pos) - len(fn_args.defaults)
        for idx, pname in enumerate(all_pos):
            if pname not in bound:
                if idx < default_start:
                    return None
                dval = self.visit(fn_args.defaults[idx - default_start])
                if dval is None or is_symbolic_ref(dval):
                    return None
                bound[pname] = self.unwrap(dval)

        for kname, dnode in zip(kwonly_names, fn_args.kw_defaults):
            if kname not in bound:
                if dnode is None:
                    return None
                dval = self.visit(dnode)
                if dval is None or is_symbolic_ref(dval):
                    return None
                bound[kname] = self.unwrap(dval)

        func_vars = [Variable(name, val) for name, val in bound.items()]

        return SafeEval(
            Context(func_vars, self.ctx),
            depth=self.depth + 1,
            max_depth=self.max_depth,
            max_allocation=self.max_allocation,
        ).visit(fn.get_body())

    def unwrap(self, obj):
        return core_unwrap(obj)

    def check_size(self, obj):
        val = self.unwrap(obj)
        if isinstance(val, (str, bytes, bytearray, list, dict, set, tuple, range)):
            try:
                if len(val) > self.max_allocation:
                    LOGGER.debug(f"Size limit exceeded for {type(val).__name__}")
                    return True
            except OverflowError:
                LOGGER.debug(f"Size overflow for {type(val).__name__}")
                return True
        elif isinstance(val, (int, float)):
            num_limit = max(self.max_allocation, 2**63 - 1)
            if val > num_limit or val < -num_limit:
                LOGGER.debug(f"Numeric limit exceeded for {type(val).__name__}")
                return True

        return False

    def visit(self, node: ast.AST | None):

        if self.depth >= self.max_depth:
            LOGGER.debug("Max recursion depth reached")
            return None

        if node is None:
            return None

        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)

        if visitor == self.generic_visit:
            return None

        return visitor(node)

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        func = LambdaType(node.body, node.args)
        wrapper = lambda *args, **kwargs: self.exec_custom_func(func, list(args), kwargs)  # type: ignore  # noqa: E731
        wrapper._noctyra_lambda = func  # type: ignore[attr-defined]
        return wrapper

    def visit_BinOp(self, node):
        left_res = self.visit(node.left)
        right_res = self.visit(node.right)

        if (
            left_res is None
            or right_res is None
            or is_symbolic_ref(left_res)
            or is_symbolic_ref(right_res)
        ):
            return None

        left = self.unwrap(left_res)
        right = self.unwrap(right_res)

        op = BIN_OPS.get(type(node.op))

        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            return None

        if op is operator.pow:
            if (
                isinstance(left, int)
                and not isinstance(left, bool)
                and isinstance(right, int)
                and not isinstance(right, bool)
            ):
                if right > 0 and abs(left) > 1 and right * abs(left).bit_length() > 128:
                    return None
                if abs(right) > 1024:
                    return None
            elif isinstance(right, (int, float)) and abs(right) > 1024:
                return None

        if op is operator.lshift:
            if isinstance(left, int) and isinstance(right, int):
                if right < 0 or right > 64 or (left != 0 and abs(left).bit_length() + right > 64):
                    return None

        if op is operator.mul:
            if isinstance(left, (str, bytes, list, tuple)) and isinstance(right, int):
                if right < 0 or len(left) * right > self.max_allocation:
                    return None
            elif isinstance(right, (str, bytes, list, tuple)) and isinstance(left, int):
                if left < 0 or len(right) * left > self.max_allocation:
                    return None

        if op is None:
            LOGGER.warning(f"Unsupported op: {type(node.op)}")
            return None

        try:
            res = op(left, right)

            if self.check_size(res):
                return None
            LOGGER.debug(
                f"BinOp: {left!r} {type(node.op).__name__} {right!r} -> {res!r}"
            )
            return res
        except Exception as e:
            LOGGER.debug(f"BinOp failed: {e}")
            return None

    def visit_Subscript(self, node: ast.Subscript):
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in ("str", "bytes")
            and self._is_builtin_usable(node.value.value.id)
        ):
            key_res = self.visit(node.slice)
            if key_res is not None and not is_symbolic_ref(key_res):
                key = self.unwrap(key_res)
                if isinstance(key, str) and key in ATTR:
                    cls = getattr(builtins, node.value.value.id)
                    return getattr(cls, key, None)
            return None

        value_res = self.visit(node.value)

        if isinstance(value_res, ImportSymbol) and value_res.module in (
            "builtins",
            "__builtins__",
        ):
            _slice_res = self.visit(node.slice)
            if _slice_res is not None and not is_symbolic_ref(_slice_res):
                _slice = self.unwrap(_slice_res)
                if isinstance(_slice, str) and _slice.isidentifier():
                    return ImportSymbol(f"{value_res.module}.{_slice}")
            return None

        if value_res is None or is_symbolic_ref(value_res):
            return None

        value = self.unwrap(value_res)
        _slice_res = self.visit(node.slice)

        if _slice_res is None or is_symbolic_ref(_slice_res):
            return None

        _slice = self.unwrap(_slice_res)

        try:
            res = value[_slice]  # type: ignore
            if self.check_size(res):
                return None
            return res
        except Exception:
            LOGGER.debug(f"Subscript failed. {value=}, {_slice=}")
            return None

    def visit_BoolOp(self, node: ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = None
            for value in node.values:
                res = self.visit(value)
                if res is None or is_symbolic_ref(res):
                    return None
                result = self.unwrap(res)
                if not result:
                    return NoneValue() if result is None else result
            return NoneValue() if result is None else result

        else:
            result = None
            for value in node.values:
                res = self.visit(value)
                if res is None or is_symbolic_ref(res):
                    return None
                result = self.unwrap(res)
                if result:
                    return result
            return NoneValue() if result is None else result

    def visit_Slice(self, node: ast.Slice):
        lower = self.visit(node.lower) if node.lower is not None else NoneValue()
        upper = self.visit(node.upper) if node.upper is not None else NoneValue()
        step = self.visit(node.step) if node.step is not None else NoneValue()

        if (
            lower is None
            or upper is None
            or step is None
            or is_symbolic_ref(lower)
            or is_symbolic_ref(upper)
            or is_symbolic_ref(step)
        ):
            return None

        if node.lower is None and node.upper is None and node.step is None:
            return slice(None, None, None)

        return slice(self.unwrap(lower), self.unwrap(upper), self.unwrap(step))

    def visit_UnaryOp(self, node: ast.UnaryOp):

        op = UNARY_OPS.get(type(node.op))

        if op is None:
            return None

        operand = self.visit(node.operand)

        if operand is None or is_symbolic_ref(operand):
            if isinstance(node.op, ast.Not) and isinstance(
                operand, (ImportSymbol, LambdaType)
            ):
                return False
            return None

        try:
            res = op(self.unwrap(operand))
            if self.check_size(res):
                return None
            return res
        except Exception:
            return None

    def visit_Call(self, node: ast.Call):

        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            if func_name in FUNCS and self._is_builtin_usable(func_name):
                func = FUNCS[func_name]
                if any(isinstance(a, ast.Starred) for a in node.args) or any(
                    kw.arg is None for kw in node.keywords
                ):
                    return None

                args_res = [self.visit(arg) for arg in node.args]
                kwargs_res = {
                    kwarg.arg: self.visit(kwarg.value)
                    for kwarg in node.keywords
                    if kwarg.arg is not None
                }
                if func is len and len(node.args) == 1 and not kwargs_res:
                    arg0 = node.args[0]
                    if (
                        args_res[0] is None
                        and isinstance(arg0, (ast.List, ast.Tuple))
                        and not any(isinstance(e, ast.Starred) for e in arg0.elts)
                        and all(_is_pure_eval_arg(e) for e in arg0.elts)
                    ):
                        return len(arg0.elts)

                if func is str and len(node.args) == 1 and not kwargs_res:
                    arg0 = node.args[0]
                    if (
                        args_res[0] is None
                        and isinstance(arg0, ast.Name)
                        and self._is_builtin_usable(arg0.id)
                    ):
                        builtin_obj = getattr(builtins, arg0.id, None)
                        if isinstance(builtin_obj, type):
                            return str(builtin_obj)

                if any(arg is None for arg in args_res):
                    return None

                if any(v is None or is_symbolic_ref(v) for v in kwargs_res.values()):
                    return None

                if func is map:
                    if len(args_res) != 2 or kwargs_res:
                        return None
                    fn = args_res[0]
                    if is_symbolic_ref(args_res[1]):
                        return None
                    arg = self.unwrap(args_res[1])
                    if isinstance(fn, LambdaType) and isinstance(
                        arg, (list, tuple, str, bytes, range, set, dict)
                    ):
                        if self.check_size(arg):
                            return None
                        mapped = [self.exec_custom_func(fn, [x]) for x in arg]
                        if any(v is None for v in mapped):
                            return None
                        return mapped
                    return None

                elif func is zip:
                    if kwargs_res or any(is_symbolic_ref(a) for a in args_res):
                        return None
                    args = [self.unwrap(a) for a in args_res]
                    for a in args:
                        if isinstance(
                            a, (list, tuple, str, bytes, range, set, dict)
                        ) and self.check_size(a):
                            return None
                    try:
                        res = list(zip(*args))
                        if self.check_size(res):
                            return None
                        return res
                    except Exception:
                        return None

                else:
                    if any(is_symbolic_ref(a) for a in args_res):
                        return None
                    try:
                        args = [self.unwrap(a) for a in args_res]
                        kwargs = {k: self.unwrap(v) for k, v in kwargs_res.items()}
                        if func in (bytes, bytearray) and not kwargs and len(args) == 1:
                            if isinstance(args[0], int) and not isinstance(
                                args[0], bool
                            ):
                                if args[0] < 0 or args[0] > self.max_allocation:
                                    return None
                        if func is pow and len(args) == 2 and not kwargs:
                            if (
                                isinstance(args[0], int)
                                and not isinstance(args[0], bool)
                                and isinstance(args[1], int)
                                and not isinstance(args[1], bool)
                            ):
                                if (
                                    args[1] > 0
                                    and abs(args[0]) > 1
                                    and args[1] * abs(args[0]).bit_length() > 128
                                ):
                                    return None
                            if (
                                isinstance(args[1], (int, float))
                                and abs(args[1]) > 1024
                            ):
                                return None
                        res = func(*args, **kwargs)

                        if self.check_size(res):
                            return None
                        LOGGER.debug(f"Call {func_name}({args}) -> {res!r}")
                        return res
                    except Exception as e:
                        LOGGER.debug(f"Call {func_name} failed: {e}")
                        return None
            elif self.ctx.has(func_name):

                func_entry = self.ctx.get(func_name)

                if func_entry is None:
                    return None

                func = func_entry.get()

                if isinstance(func, ImportSymbol) and "." in func.module:
                    if func.module in ("builtins.__import__", "__builtins__.__import__"):
                        if len(node.args) == 1 and not node.keywords:
                            arg_res = self.visit(node.args[0])
                            if arg_res is not None and not is_symbolic_ref(arg_res):
                                mod_arg = self.unwrap(arg_res)
                                if isinstance(mod_arg, str):
                                    return ImportSymbol(mod_arg)
                        return None
                    mod_name, attr_name = func.module.rsplit(".", 1)
                    return self._call_whitelisted(mod_name, attr_name, node)

                if (
                    callable(func)
                    and getattr(func, "__name__", None) in ATTR
                    and isinstance(getattr(func, "__self__", None), (str, bytes))
                ):
                    return self._call_bound_attr(
                        func.__self__, func.__name__, node  # type: ignore[attr-defined]
                    )

                if not isinstance(func, LambdaType):
                    return None

                return self._eval_custom_func_call(func, node)

            elif (
                self._is_builtin_usable(func_name)
                and len(node.args) == 1
                and not node.keywords
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):

                if func_name == "eval":
                    try:
                        parsed = ast.parse(node.args[0].value, mode="eval")
                    except SyntaxError:
                        return None
                    return self.visit(parsed.body)

                elif func_name == "__import__":
                    return ImportSymbol(node.args[0].value)

            elif (
                func_name == "vars"
                and self._is_builtin_usable("vars")
                and len(node.args) == 1
                and not node.keywords
            ):
                arg_res = self.visit(node.args[0])
                if isinstance(arg_res, ImportSymbol) and arg_res.module in (
                    "builtins",
                    "__builtins__",
                ):
                    return ImportSymbol("__builtins__")

        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr

            if (
                attr_name == "fromhex"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "bytes"
                and self._is_builtin_usable("bytes")
                and len(node.args) == 1
                and not node.keywords
            ):
                arg_res = self.visit(node.args[0])
                if arg_res is not None and not is_symbolic_ref(arg_res):
                    arg_val = self.unwrap(arg_res)
                    if isinstance(arg_val, str) and len(arg_val) <= self.max_allocation * 2:
                        try:
                            hex_res = bytes.fromhex(arg_val)
                            if self.check_size(hex_res):
                                return None
                            return hex_res
                        except ValueError:
                            return None

            if (
                attr_name == "__get__"
                and len(node.args) in (1, 2)
                and not node.keywords
            ):
                descr = self.visit(node.func.value)
                d_name = getattr(descr, "__name__", None)
                d_cls = getattr(descr, "__objclass__", None)
                if d_name in ATTR and d_cls in (str, bytes):
                    inst_res = self.visit(node.args[0])
                    if inst_res is not None and not is_symbolic_ref(inst_res):
                        inst = self.unwrap(inst_res)
                        if isinstance(inst, d_cls):
                            return descr.__get__(inst)
                return None

            if (
                attr_name in ATTR
                and not node.keywords
                and not any(isinstance(a, ast.Starred) for a in node.args)
            ):
                val_res = self.visit(node.func.value)
                if val_res is not None and not is_symbolic_ref(val_res):
                    value = self.unwrap(val_res)
                    return self._call_bound_attr(value, attr_name, node)

            module = self.visit(node.func.value)

            if isinstance(module, ImportSymbol):
                return self._call_whitelisted(module.module, attr_name, node)

            return None

        else:
            func_val = self.visit(node.func)
            if isinstance(func_val, LambdaType):
                return self._eval_custom_func_call(func_val, node)
            if isinstance(
                wrapped_fn := getattr(func_val, "_noctyra_lambda", None), LambdaType
            ):
                return self._eval_custom_func_call(wrapped_fn, node)
            if isinstance(func_val, ImportSymbol) and "." in func_val.module:
                mod_name, attr_name = func_val.module.rsplit(".", 1)
                return self._call_whitelisted(mod_name, attr_name, node)
            return None

    def _eval_custom_func_call(self, func: LambdaType, node: ast.Call) -> Any:
        if any(isinstance(a, ast.Starred) for a in node.args) or any(
            kw.arg is None for kw in node.keywords
        ):
            return None

        args_res = [self.visit(arg) for arg in node.args]
        kwargs_res = {
            kwarg.arg: self.visit(kwarg.value)
            for kwarg in node.keywords
            if kwarg.arg is not None
        }

        for arg_node, arg_val in zip(node.args, args_res):
            if arg_val is None and not _is_pure_eval_arg(arg_node):
                return None

        for kw_node, kw_val in zip(
            (kw.value for kw in node.keywords if kw.arg is not None),
            kwargs_res.values(),
        ):
            if kw_val is None and not _is_pure_eval_arg(kw_node):
                return None

        args = [_UNBOUND_ARG if a is None else self.unwrap(a) for a in args_res]
        kwargs = {
            k: (_UNBOUND_ARG if v is None else self.unwrap(v))
            for k, v in kwargs_res.items()
        }

        res = self.exec_custom_func(func, args, kwargs)  # type: ignore
        if res is not None and self.check_size(res):
            return None
        return res

    def _call_bound_attr(self, value: Any, attr_name: str, node: ast.Call) -> Any:
        if node.keywords or any(isinstance(a, ast.Starred) for a in node.args):
            return None
        try:
            args_res = [self.visit(arg) for arg in node.args]
            if any(arg is None or is_symbolic_ref(arg) for arg in args_res):
                return None

            args = [self.unwrap(a) for a in args_res]
            if attr_name == "join" and isinstance(value, str) and len(args) == 1:
                seq = args[0]
                if isinstance(seq, (list, tuple, set)):
                    est = sum(len(s) for s in seq if isinstance(s, str)) + len(
                        value
                    ) * max(0, len(seq) - 1)
                    if est > self.max_allocation:
                        return None
                elif isinstance(seq, str):
                    if len(seq) * (len(value) + 1) > self.max_allocation:
                        return None

            func = getattr(value, attr_name)
            result = func(*args)

            if not isinstance(result, supported_types):
                return None

            if self.check_size(result):
                return None

            LOGGER.debug(
                f"Attr call: {type(value).__name__}.{attr_name} -> {result!r}"
            )
            return result
        except Exception:
            return None

    def _call_whitelisted(
        self, mod_name: str, attr_name: str, node: ast.Call
    ) -> Any:
        if mod_name not in WHITELIST or attr_name not in WHITELIST[mod_name]:
            return None

        if node.keywords or any(isinstance(a, ast.Starred) for a in node.args):
            return None

        func = WHITELIST[mod_name][attr_name]
        args_res = [self.visit(arg) for arg in node.args]

        if any(arg is None or is_symbolic_ref(arg) for arg in args_res):
            return None

        args = [self.unwrap(a) for a in args_res]

        try:
            if (
                mod_name in {"zlib", "gzip", "bz2", "lzma", "brotli", "blosc", "zstd"}
                and attr_name == "decompress"
            ):
                if len(args) != 1 or not isinstance(args[0], (bytes, bytearray)):
                    return None
                if mod_name == "zlib":
                    d_zlib = zlib.decompressobj()
                    result = d_zlib.decompress(
                        args[0], max_length=self.max_allocation
                    )
                    if d_zlib.unconsumed_tail:
                        LOGGER.debug("zlib decompression exceeded max_allocation")
                        return None
                elif mod_name == "gzip":
                    d_gzip = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
                    result = d_gzip.decompress(
                        args[0], max_length=self.max_allocation
                    )
                    if d_gzip.unconsumed_tail:
                        LOGGER.debug("gzip decompression exceeded max_allocation")
                        return None
                elif mod_name == "bz2":
                    d_bz2 = bz2.BZ2Decompressor()
                    result = d_bz2.decompress(
                        args[0], max_length=self.max_allocation
                    )
                    if not d_bz2.eof:
                        LOGGER.debug("bz2 decompression exceeded max_allocation")
                        return None
                elif mod_name == "lzma":
                    d_lzma = lzma.LZMADecompressor()
                    result = d_lzma.decompress(
                        args[0], max_length=self.max_allocation
                    )
                    if not d_lzma.eof:
                        LOGGER.debug("lzma decompression exceeded max_allocation")
                        return None
                elif mod_name == "brotli":
                    d_brotli = brotli.Decompressor()
                    result = d_brotli.process(
                        bytes(args[0]), output_buffer_limit=self.max_allocation
                    )
                    if not d_brotli.is_finished() or len(result) > self.max_allocation:
                        LOGGER.debug("brotli decompression exceeded max_allocation")
                        return None
                elif mod_name == "blosc":
                    nbytes, _, _ = blosc.get_cbuffer_sizes(args[0])
                    if nbytes > self.max_allocation:
                        LOGGER.debug("blosc decompression exceeded max_allocation")
                        return None
                    result = func(*args)
                else:  # zstd
                    raw_z = bytes(args[0])
                    if _stdlib_zstd is not None:
                        d_zstd = _stdlib_zstd.ZstdDecompressor()
                        result = d_zstd.decompress(
                            raw_z, max_length=self.max_allocation
                        )
                        if not d_zstd.eof:
                            LOGGER.debug("zstd decompression exceeded max_allocation")
                            return None
                    else:
                        if not _is_zstd_single_frame_bounded(
                            raw_z, self.max_allocation
                        ):
                            LOGGER.debug("zstd frame missing bounded size header")
                            return None
                        result = func(*args)
            elif mod_name == "math" and attr_name == "factorial":
                if (
                    len(args) != 1
                    or not isinstance(args[0], int)
                    or isinstance(args[0], bool)
                    or args[0] < 0
                    or args[0] > min(self.max_allocation, 1000)
                ):
                    return None
                result = func(args[0])
            else:
                result = func(*args)
            if not isinstance(result, supported_types):
                return None

            if self.check_size(result):
                return None

            LOGGER.debug(
                f"Resolved encoding call: {mod_name}.{attr_name} -> {result!r}"
            )
            return result  # type: ignore
        except Exception as e:
            LOGGER.debug(f"Failed to resolve encoding call: {e}")

        return None

    def visit_Constant(self, node: ast.Constant):
        if node.value is None:
            return NoneValue()
        return SymbolicValue(node.value)

    def visit_Name(self, node: ast.Name):
        if (entry := self.ctx.get(node.id)) is not None:
            result = entry.get()
            return result

        if node.id == "__builtins__" and self._is_builtin_usable("__builtins__"):
            return ImportSymbol("__builtins__")

        if node.id == "__import__" and self._is_builtin_usable("__import__"):
            return ImportSymbol("builtins.__import__")

        return None

    def visit_Attribute(self, node: ast.Attribute):
        value_res = self.visit(node.value)
        if isinstance(value_res, ImportSymbol):
            base = (
                "builtins"
                if value_res.module in ("builtins", "__builtins__")
                else value_res.module
            )
            return ImportSymbol(f"{base}.{node.attr}")
        return None

    def visit_List(self, node: ast.List):
        res = [self.visit(elt) for elt in node.elts]
        if any(v is None for v in res):
            return None
        if self.check_size(res):
            return None
        return res

    def visit_Set(self, node: ast.Set):
        res_items = [self.visit(elt) for elt in node.elts]
        if any(v is None for v in res_items):
            return None
        try:
            res = set(res_items)
        except TypeError:
            return None
        if self.check_size(res):
            return None
        return res

    def visit_Tuple(self, node: ast.Tuple):
        res = tuple([self.visit(elt) for elt in node.elts])
        if any(v is None for v in res):
            return None
        if self.check_size(res):
            return None
        return res

    def visit_Dict(self, node: ast.Dict):
        if any(k is None for k in node.keys):
            return None
        res: dict[Any, Any] = {}
        for k_node, v_node in zip(node.keys, node.values):
            assert k_node is not None
            k_res = self.visit(k_node)
            v_res = self.visit(v_node)
            if k_res is None or v_res is None or is_symbolic_ref(k_res):
                return None
            k_val = self.unwrap(k_res)
            try:
                res[k_val] = v_res
            except TypeError:
                return None
        if self.check_size(res):
            return None
        return res

    @staticmethod
    def _bind_comp_target(
        target: ast.AST, val: Any, env: dict[str, Any]
    ) -> bool:
        if isinstance(target, ast.Name):
            env[target.id] = val
            return True
        if isinstance(target, (ast.Tuple, ast.List)) and not any(
            isinstance(e, ast.Starred) for e in target.elts
        ):
            if not isinstance(val, (tuple, list)) or len(target.elts) != len(val):
                return False
            return all(
                SafeEval._bind_comp_target(t, item, env)
                for t, item in zip(target.elts, val)
            )
        return False

    def _eval_comprehension(
        self, elt: ast.expr, generators: list[ast.comprehension]
    ) -> list[Any] | None:
        if self.depth >= self.max_depth or not generators:
            return None
        if any(g.is_async for g in generators):
            return None

        results: list[Any] = []

        def _recurse(gen_idx: int, cur_ctx: Context) -> bool:
            if gen_idx == len(generators):
                sub_eval = SafeEval(
                    cur_ctx,
                    depth=self.depth + 1,
                    max_depth=self.max_depth,
                    max_allocation=self.max_allocation,
                )
                val_res = sub_eval.visit(elt)
                if val_res is None or is_symbolic_ref(val_res):
                    return False
                results.append(self.unwrap(val_res))
                return len(results) <= self.max_allocation

            gen = generators[gen_idx]
            iter_eval = SafeEval(
                cur_ctx,
                depth=self.depth + 1,
                max_depth=self.max_depth,
                max_allocation=self.max_allocation,
            )
            iter_res = iter_eval.visit(gen.iter)
            if iter_res is None or is_symbolic_ref(iter_res):
                return False
            iterable = self.unwrap(iter_res)
            if not isinstance(
                iterable, (list, tuple, str, bytes, range, set, dict)
            ) or self.check_size(iterable):
                return False

            for item in iterable:
                env: dict[str, Any] = {}
                if not self._bind_comp_target(gen.target, item, env):
                    return False
                next_ctx = Context(
                    [Variable(k, v) for k, v in env.items()], cur_ctx
                )
                if gen.ifs:
                    cond_eval = SafeEval(
                        next_ctx,
                        depth=self.depth + 1,
                        max_depth=self.max_depth,
                        max_allocation=self.max_allocation,
                    )
                    passed = True
                    for cond_node in gen.ifs:
                        c_res = cond_eval.visit(cond_node)
                        if c_res is None or is_symbolic_ref(c_res):
                            return False
                        if not bool(self.unwrap(c_res)):
                            passed = False
                            break
                    if not passed:
                        continue
                if not _recurse(gen_idx + 1, next_ctx):
                    return False
            return True

        if not _recurse(0, self.ctx):
            return None
        return results

    def visit_ListComp(self, node: ast.ListComp):
        return self._eval_comprehension(node.elt, node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        return self._eval_comprehension(node.elt, node.generators)

    def visit_IfExp(self, node: ast.IfExp):

        cond_res = self.visit(node.test)

        if cond_res is None or is_symbolic_ref(cond_res):
            body_res = self.visit(node.body)
            orelse_res = self.visit(node.orelse)
            if (
                isinstance(body_res, ImportSymbol)
                and isinstance(orelse_res, ImportSymbol)
                and body_res.module == orelse_res.module
            ):
                return body_res
            return None

        cond = self.unwrap(cond_res)

        result = self.visit(node.body) if cond else self.visit(node.orelse)

        return result

    def visit_Compare(self, node: ast.Compare):

        if len(node.ops) != len(node.comparators):
            return None

        try:
            left_res = self.visit(node.left)
            if left_res is None or is_symbolic_ref(left_res):
                return None

            left = self.unwrap(left_res)

            for i, op in enumerate(node.ops):
                right_res = self.visit(node.comparators[i])
                if right_res is None or is_symbolic_ref(right_res):
                    return None

                right = self.unwrap(right_res)

                fn = COMP_OPS.get(type(op))
                if fn is None:
                    return None

                if not fn(left, right):
                    return False
                left = right

            return True
        except Exception as e:
            LOGGER.debug(f"Compare failed: {e}")
            return None

    def visit_FormattedValue(self, node: ast.FormattedValue):
        val_res = self.visit(node.value)
        if val_res is None:
            return None

        if is_symbolic_ref(val_res):
            return None

        val = self.unwrap(val_res)

        try:
            if node.conversion == 115:  # !s
                val = str(val)
            elif node.conversion == 114:  # !r
                val = repr(val)
            elif node.conversion == 97:  # !a
                val = ascii(val)

            if node.format_spec is not None:
                spec_res = self.visit(node.format_spec)
                if spec_res is None:
                    return None
                spec = self.unwrap(spec_res)
                if not isinstance(spec, str):
                    return None
                for num_str in re.findall(r"\d+", spec):
                    if int(num_str) > self.max_allocation:
                        return None
                formatted = format(val, spec)
            else:
                formatted = str(val)

            if self.check_size(formatted):
                return None

            return formatted
        except Exception as e:
            LOGGER.debug(f"FormattedValue failed: {e}")
            return None

    def visit_JoinedStr(self, node: ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            res = self.visit(value)
            if res is None:
                return None
            unwrapped = self.unwrap(res)
            if not isinstance(unwrapped, str):
                return None
            parts.append(unwrapped)

        joined = "".join(parts)
        if self.check_size(joined):
            return None

        LOGGER.debug(f"Evaluated JoinedStr -> {joined!r}")
        return joined


def safe_eval(
    node: ast.AST | None,
    ctx: Context | None = None,
    max_depth: int = 50,
    max_allocation: int = 100_000,
) -> None | Any:

    return SafeEval(ctx, max_depth=max_depth, max_allocation=max_allocation).visit(node)
