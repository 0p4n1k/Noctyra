from types import FunctionType, MethodType
import binascii
import operator
import marshal
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

OPS = {
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
}

encoding: dict[str, dict[str, FunctionType | MethodType]] = {
    'base64': {
        'b16decode': base64.b16decode,
        'b32decode': base64.b32decode,
        'b64decode': base64.b64decode,
        'b85decode': base64.b85decode,
        'a85decode': base64.a85decode
    },
    'zlib': {
        'decompress': zlib.decompress
    },
    'gzip': {
        'decompress': gzip.decompress
    },
    'lzma': {
        'decompress': lzma.decompress
    },
    'bz2': {
        'decompress': bz2.decompress
    },
    'brotli': {
        'decompress': brotli.decompress
    },
    'zstd': {
        'decompress': zstd.decompress
    },
    'blosc': {
        'decompress': blosc.decompress
    },
    'bytes': {
        'fromhex': bytes.fromhex
    },
    'marshal': {
        'loads': marshal.loads
    },
    'binascii': {
        'unhexlify': binascii.unhexlify
    },
    'codecs': {
        'decode': codecs.decode
    }
}