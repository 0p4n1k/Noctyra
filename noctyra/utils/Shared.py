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
import lzma
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

ENCODING: dict[str, dict[str, Callable[..., bytes]]] = {
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
    "codecs": {"decode": codecs.decode},
}
