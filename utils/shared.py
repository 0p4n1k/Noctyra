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
import lzma
import bz2
import ast

ATTR: dict[str, Callable] = {
    "decode": bytes.decode,
    "encode": str.encode,
    "hex": bytes.hex,
    "join": str.join,
    "isalpha": str.isalpha,
    "isdigit": str.isdigit,
    "isupper": str.isupper,
    "upper": str.upper,
    "lower": str.lower,
}

FUNCS: dict[str, Callable] = {
    "ord": ord,
    "chr": chr,
    "hex": hex,
    "int": int,
    "float": float,
    "str": str,
    "bytes": bytes,
}

OPS: dict[Any, Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
    ast.Lt: operator.lt,
    ast.Gt: operator.gt,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.LtE: operator.le,
    ast.GtE: operator.ge,
    ast.And: operator.and_,
    ast.Or: operator.or_,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.UnaryOp: operator.neg,
    ast.USub: operator.neg,
    ast.FloorDiv: operator.floordiv,
}

encoding: dict[str, dict[str, Callable[..., bytes]]] = {
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
