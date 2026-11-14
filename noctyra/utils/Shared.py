from typing import Callable, Any
import binascii
import operator
import base64
import brotli
import codecs
import blosc
import zstd
import zlib
import gzip
import html
import lzma
import math
import bz2
import ast

IMMUTABLE_TYPES = (int, float, str, bytes, bool, type(None))

ATTR: dict[str, Callable] = {
    "decode": bytes.decode,
    "encode": str.encode,
    "hex": bytes.hex,
    "join": str.join,
    "isalpha": str.isalpha,
    "isdigit": str.isdigit,
    "islower": str.islower,
    "isupper": str.isupper,
    "upper": str.upper,
    "lower": str.lower,
    "split": str.split,
    "strip": str.strip,
    "startswith": str.startswith,
}

FUNCS: dict[str, Callable] = {
    "ord": ord,
    "chr": chr,
    "hex": hex,
    "int": int,
    "float": float,
    "str": str,
    "bytes": bytes,
    "bytearray": bytearray,
    "map": map,
    "list": list,
    "pow": pow,
    "zip": zip,
    "all": all,
    "round": round,
    "range": range,
    "len": len,
}

BIN_OPS: dict[Any, Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}

UNARY_OPS: dict[Any, Callable] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
    ast.Invert: operator.invert,
}

COMP_OPS: dict[Any, Callable] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda x, y: x in y,
    ast.NotIn: lambda x, y: x not in y,
}

_SAFE_CODECS = frozenset(
    {
        "utf-8",
        "utf8",
        "ascii",
        "latin-1",
        "latin1",
        "iso-8859-1",
        "rot_13",
        "rot-13",
        "rot13",
        "hex",
        "hex_codec",
        "base64",
        "base64_codec",
        "quopri",
        "quopri_codec",
        "uu",
        "uu_codec",
    }
)


def _safe_codecs_decode(
    obj: Any, encoding: str = "utf-8", errors: str = "strict"
) -> Any:
    if encoding.lower().strip() not in _SAFE_CODECS:
        raise ValueError(f"Codec '{encoding}' is not in safe whitelist")
    return codecs.decode(obj, encoding, errors)


WHITELIST: dict[str, dict[str, Callable[..., Any]]] = {
    "base64": {
        "b16decode": base64.b16decode,
        "b32decode": base64.b32decode,
        "b64decode": base64.b64decode,
        "b85decode": base64.b85decode,
        "a85decode": base64.a85decode,
    },
    "zlib": {"decompress": zlib.decompress},
    "gzip": {"decompress": gzip.decompress},
    "lzma": {"decompress": lzma.decompress},
    "bz2": {"decompress": bz2.decompress},
    "brotli": {"decompress": brotli.decompress},
    "zstd": {"decompress": zstd.decompress},
    "blosc": {"decompress": blosc.decompress},
    "bytes": {"fromhex": bytes.fromhex},
    "binascii": {"unhexlify": binascii.unhexlify},
    "codecs": {"decode": _safe_codecs_decode},
    "html": {"unescape": html.unescape},
    "math": {
        "sqrt": math.sqrt,
        "floor": math.floor,
        "ceil": math.ceil,
        "fabs": math.fabs,
        "factorial": math.factorial,
        "gcd": math.gcd,
        "log": math.log,
        "log2": math.log2,
        "log10": math.log10,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "pow": math.pow,
    },
}


def is_pure_expr(node: ast.AST, *, allow_containers: bool = False) -> bool:
    """Return True if evaluating node has no observable side effects (modulo NameError)."""
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, ast.UnaryOp):
        return is_pure_expr(node.operand, allow_containers=allow_containers)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            return False
        if isinstance(node.op, (ast.Pow, ast.LShift)) and not (
            isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, int)
            and not isinstance(node.right.value, bool)
            and 0 <= node.right.value <= 64
        ):
            return False
        return is_pure_expr(
            node.left, allow_containers=allow_containers
        ) and is_pure_expr(node.right, allow_containers=allow_containers)
    if isinstance(node, ast.BoolOp):
        return all(
            is_pure_expr(v, allow_containers=allow_containers) for v in node.values
        )
    if isinstance(node, ast.Compare):
        return is_pure_expr(node.left, allow_containers=allow_containers) and all(
            is_pure_expr(c, allow_containers=allow_containers)
            for c in node.comparators
        )
    if isinstance(node, ast.IfExp):
        return (
            is_pure_expr(node.test, allow_containers=allow_containers)
            and is_pure_expr(node.body, allow_containers=allow_containers)
            and is_pure_expr(node.orelse, allow_containers=allow_containers)
        )
    if isinstance(node, ast.JoinedStr):
        return all(
            isinstance(v, ast.Constant)
            or (
                isinstance(v, ast.FormattedValue)
                and is_pure_expr(v.value, allow_containers=allow_containers)
                and (
                    v.format_spec is None
                    or is_pure_expr(v.format_spec, allow_containers=allow_containers)
                )
            )
            for v in node.values
        )
    if allow_containers:
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(is_pure_expr(e, allow_containers=True) for e in node.elts)
        if isinstance(node, ast.Dict):
            return all(
                (k is None or is_pure_expr(k, allow_containers=True))
                and is_pure_expr(v, allow_containers=True)
                for k, v in zip(node.keys, node.values)
            )
    return False


def is_pure_stmt(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr):
        return is_pure_expr(stmt.value)
    if isinstance(stmt, ast.Assign):
        return all(isinstance(t, ast.Name) for t in stmt.targets) and is_pure_expr(
            stmt.value
        )
    return False
