from typing import Callable, Any
import binascii
import operator
import hashlib
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

h = hashlib.sha256()

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
    "hexdigest": lambda x: x,
}

FUNCS: dict[str, Callable] = {
    "ord": ord,
    "chr": chr,
    "hex": hex,
    "int": int,
    "float": float,
    "str": str,
    "bytes": bytes,
    "map": map,
    "list": list,
    "pow": pow,
    "zip": zip,
    "all": all,
    "round": round,
    "filter": filter,
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
