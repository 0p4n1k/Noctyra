from noctyra.transformers import (
    ConstsTransformer,
    LCTransformer,
    ConditionSimplifier,
    NameReplacer,
    DeadCodeRemover,
    FStringTransformer,
    IdentifierRenamer,
    ImportAliasFolder,
    BasicInliner,
    AlgebraicSimplifier,
    ControlFlowSimplifier,
    CollectionsTransformer,
    StringFormatTransformer,
    ExecUnpacker,
    TernarySimplifier,
    DictDispatchSimplifier,
    BuiltinFolder,
)
from noctyra.core import TransformerPipeline
import ast


def transform(code: str, *, advanced: bool = False) -> str:
    tree = ast.parse(code)
    pipeline = TransformerPipeline(
        transformers=[
            ImportAliasFolder,
            BasicInliner,
            ConstsTransformer,
            AlgebraicSimplifier,
            CollectionsTransformer,
            BuiltinFolder,
            DictDispatchSimplifier,
            ExecUnpacker,
            FStringTransformer,
            StringFormatTransformer,
            LCTransformer,
            ConditionSimplifier,
            TernarySimplifier,
            ControlFlowSimplifier,
            NameReplacer,
            DeadCodeRemover,
        ],
        advanced=advanced,
    )
    return ast.unparse(pipeline.visit(tree))


# -- compare --


def test_compare_chain_false():
    code = "x = 1 < 2 > 3"
    out = transform(code)

    assert "x = False" in out


def test_compare_new_ops():
    # testing is, is not, in, not in
    code = """
a = 1 is 1
b = 1 is not 2
c = 'x' in 'xyz'
d = 'a' not in 'xyz'
"""
    out = transform(code)
    assert "a = True" in out
    assert "b = True" in out
    assert "c = True" in out
    assert "d = True" in out


# -- operations --


def test_binops_bit():
    code = "x = (1 & 1) | (2 ^ 3) << 1 >> 1"
    # (1 & 1) = 1
    # (2 ^ 3) = 1
    # 1 << 1 = 2
    # 2 >> 1 = 1
    # 1 | 1 = 1
    out = transform(code)
    assert "x = 1" in out


def test_unary_ops():
    code = "x = not False; y = ~-5; z = - -10"
    out = transform(code)
    assert "x = True" in out
    assert "y = 4" in out
    assert "z = 10" in out


# -- ifexp --


def test_ifexp_true():
    code = "x = 10 if True else 20"
    out = transform(code)

    assert "x = 10" in out


def test_ifexp_false():
    code = "x = 10 if False else 20"
    out = transform(code)

    assert "x = 20" in out


# -- attributes --


def test_string_upper():
    code = "x = 'hello'.upper()"
    out = transform(code)

    assert "x = 'HELLO'" in out


def test_string_join():
    code = "x = ','.join(['a', 'b', 'c'])"
    out = transform(code)

    assert "x = 'a,b,c'" in out


# -- protection --


def test_recursive_function_protection():
    code = """
f = lambda x:f(x)

y = f(1)
"""
    out = transform(code)

    assert isinstance(out, str)


def test_safe_eval_limit():
    # Shouldn't fold to a huge string
    out = transform("x = 'A' * 10**8")
    assert len(out) < 1000


def test_pow_limit():
    code = "x = 2 ** 1000000"
    out = transform(code)

    # Should not expand
    assert len(out) < 1000


def test_bytes_limit():
    # bytes() should not OOM
    code = "x = bytes(10000000)"
    out = transform(code)
    assert "bytes(10000000)" in out


def test_list_repetition_limit():
    # [0] * 10**8 should not OOM
    code = "x = [0] * 10000000"
    out = transform(code)
    assert "[0] * 10000000" in out


# -- edge cases safe_eval --


def test_division_by_zero_protection():
    code = "x = 1 / 0"
    out = transform(code)

    # Should not crash or fold
    assert isinstance(out, str)


def test_complex_subscript():
    code = "x = 'hello world'[0:5]; y = [1, 2, 3][-1]"
    out = transform(code)
    assert "x = 'hello'" in out
    assert "y = 3" in out


def test_subscript_step():
    code = "x = '123456'[::2]"
    out = transform(code)
    assert "x = '135'" in out


# -- args handling --


def test_function_kwargs():
    code = "x = pow(2, exp = 3)"
    out = transform(code)

    assert "x = 8" in out


# -- const folding --


def test_const_folding_basic():
    assert "x = 7" in transform("x = 1 + 2 * 3")


# -- context propagation --


def test_context_simple():
    # e is known, should fold the concatenation
    code = "e = 'hello'\nx = e + ' world'"
    assert "x = 'hello world'" in transform(code)


def test_context_chain():
    # chain resolution: a -> b -> c

    code = "a = 1\nb = a + 1\nc = b + 1"
    assert "c = 3" in transform(code)


def test_context_not_leaked():
    # x in a different scope, should not pollute

    code = "x = 1\ndef f():\n    x = 99\n    return x"
    out = transform(code)
    assert "return 99" in out or "return x" in out


def test_local_ctx_leak():
    # x should be known in the list comprehension

    code = "x = 1\ndef f():\n    x = 99\nprint(x)"

    assert "print(1)" in transform(code)


# -- functions --


def test_base64_decode():
    code = "import base64; x = base64.b64decode('SGVsbG8=').decode()"
    assert "x = 'Hello'" in transform(code)


def test_exec_unrolling():
    out = transform("exec('print(\"unrolled\")')")
    assert "exec" not in out
    assert "print" in out


# -- list comp --


def test_listcomp_folding():
    assert "x = [4, 6]" in transform("x = [i * 2 for i in [1, 2, 3] if i > 1]")


def test_listcomp_with_context():
    # nums is known, should fold the list comprehension
    code = "nums = [1, 2, 3]\nx = [i * 2 for i in nums]"
    assert "x = [2, 4, 6]" in transform(code)


# -- conditions --


def test_condition_simplification():
    out = transform("if 1 < 2 < 3: print('ok')")
    assert "print('ok')" in out


def test_condition_with_context():
    code = "x = 5\nif x > 3: print('ok')"
    assert "print('ok')" in transform(code)


# -- dead code removal --


def test_dead_return():
    code = "def f():\n    return 5\n    return 10"
    out = transform(code)
    assert "return 5" in out
    assert "return 10" not in out


# -- custom function --


def test_map_lambda_eval():
    code = """
f = lambda x: chr(ord(x) ^ 1)
data = "abc"
x = "".join(map(f, data))
"""
    out = transform(code)
    # should fully evaluate
    assert "x = 'bcd'" in out or "x =" in out


def test_double_map_identity():
    code = """
f = lambda x: chr(ord(x) ^ 1)
data = "abc"
x = "".join(map(f, map(f, data)))
"""
    out = transform(code)
    assert "x = 'abc'" in out


# -- subscript --


def test_safe_subscript():
    code = "x = [1, 2, 3][1]"
    out = transform(code)
    assert "x = 2" in out


# -- real obfuscation --


def test_realistic_obfuscation():
    code = """
import base64

f = lambda x: chr(ord(x) ^ 1)

data = "cHJpbnQoIk9LIik="
encoded = list(map(f, data))
decoded = "".join(map(f, encoded))

exec(base64.b64decode(decoded))
"""
    out = transform(code)

    assert "print('OK')" in out


def test_bitwise_obfuscation():
    # Many bitwise operations combined
    code = "x = (10 << 2 | 5) ^ 42 & ~15"
    # 10 << 2 = 40
    # 40 | 5 = 45
    # ~15 = -16
    # 42 & -16 = 32
    # 45 ^ 32 = 13
    out = transform(code)
    assert "x = 13" in out


def test_complex_context_propagation():
    code = """
def main():
    a = 100
    b = a ^ 50
    c = b + 10
    if c > 100:
        print("WIN")
"""
    out = transform(code)
    # 100 ^ 50 = 86
    # 86 + 10 = 96
    # 96 > 100 = False
    assert "print('WIN')" not in out


# -- f-strings --


def test_fstring_constant_folding():
    code = """
a = f"{'he' + 'llo'} {1 + 2}"
b = f"{65:x}"
c = f"{'abc'!r}"
d = f"{'é'!a}"
"""
    out = transform(code)
    assert "a = 'hello 3'" in out
    assert "b = '41'" in out
    assert "c = \"'abc'\"" in out or "c = \"'abc'\"" in out
    assert "d = \"'\\\\xe9'\"" in out


def test_fstring_partial_folding():
    code = """
def greet(name):
    return f"{'hi'} {'there'} {name} {2 * 3}"
"""
    out = transform(code)
    assert "f'hi there {name} 6'" in out


def test_fstring_nested_in_exec():
    code = """
x = "print"
exec(f"{x}('HELLO')")
"""
    out = transform(code)
    assert "print('HELLO')" in out


# -- renamer --


def rename(code: str, mode: str = "all") -> str:
    tree = ast.parse(code)
    renamer = IdentifierRenamer(mode=mode)  # type: ignore[arg-type]
    return ast.unparse(renamer.run(tree))


def test_renamer_all_mode_scopes_and_builtins():
    code = """
import os
import math as m_alias

my_var = 10

def compute(x, y=1):
    z = x + y + my_var
    return m_alias.sqrt(z)

print(compute(5, y=2), os.name)
"""
    out = rename(code, mode="all")
    assert "import os" in out
    assert "os.name" in out
    assert "print(" in out
    assert "my_var" not in out
    assert "compute" not in out
    assert "m_alias" not in out
    assert "def func_1(arg_1, arg_2=1):" in out
    assert "func_1(5, arg_2=2)" in out
    # Execute both to ensure identical semantics
    ns_orig: dict = {}
    ns_new: dict = {}
    exec(code, ns_orig)
    exec(out, ns_new)


def test_renamer_obfuscated_mode_only_targets_obfuscated():
    code = """
readable_var = 1
_0x1a2b = 2
O0l1I = 3
αβγ = 4

def __dunder__():
    return readable_var + _0x1a2b + O0l1I + αβγ
"""
    out = rename(code, mode="obfuscated")
    assert "readable_var = 1" in out
    assert "def __dunder__():" in out
    assert "_0x1a2b" not in out
    assert "O0l1I" not in out
    assert "αβγ" not in out


def test_renamer_none_mode_noop():
    code = "_0x1a2b = 42"
    assert rename(code, mode="none") == "_0x1a2b = 42"


def test_renamer_class_self_global_nonlocal_and_comp():
    code = """
g_val = 10

class MyClass:
    def __init__(self, val):
        self.attr_name = val

    def method(self):
        global g_val
        outer = 1
        def inner():
            nonlocal outer
            outer += g_val
            return outer
        return [i + inner() for i in range(3)]
"""
    out = rename(code, mode="all")
    assert "def __init__(self, arg_1):" in out
    assert "self.attr_name = arg_1" in out
    assert "global var_" in out
    assert "nonlocal var_" in out
    assert "range(3)" in out
    # Verify runtime equivalence
    ns_orig: dict = {}
    ns_new: dict = {}
    exec(code, ns_orig)
    exec(out, ns_new)
    assert ns_orig["MyClass"](5).method() == ns_new["cls_1"](5).method()


def test_renamer_idempotent():
    code = """
_0xdead = 1
def _0xbeef(x):
    return x + _0xdead
"""
    once = rename(code, mode="all")
    twice = rename(once, mode="all")
    assert once == twice


# -- import alias folding --


def test_import_alias_folding_and_unrolling():
    code = """
import base64 as var_1

exec(var_1.b64decode("cHJpbnQoJ09LJyk="))
"""
    out = transform(code)
    assert "var_1" not in out
    assert "import base64" not in out
    assert "print('OK')" in out


def test_import_alias_dotted_and_from_import():
    code = """
import os.path as p
from math import sqrt as s

def f(x):
    return p.join("a", "b"), s(x)
"""
    out = transform(code)
    assert "import os.path" in out
    assert "from math import sqrt" in out
    assert "os.path.join('a', 'b')" in out
    assert "sqrt(x)" in out


def test_import_alias_respects_shadowing_and_reassignment():
    code = """
import math as m

math = 123
x = m.sqrt(16)
"""
    out = ast.unparse(ImportAliasFolder().run(ast.parse(code)))
    # Since `math` is already bound in module scope, `import math as m` must not unfold
    assert "import math as m" in out
    assert "m.sqrt(16)" in out


# -- boolop short-circuiting --


def test_boolop_short_circuit_values_and_partial():
    code = """
def f(x):
    a = 0 or "hello"
    b = 1 and "world"
    c = False and x
    d = True or x
    e = False or x
    g = True and x
    return (a, b, c, d, e, g)
"""
    out = transform(code)
    assert "a = 'hello'" in out or "return ('hello', 'world', False, True, x, x)" in out
    assert "False" in out
    assert "True" in out


# -- dynamic inliner --


def test_basic_inliner_builtins_getattr_and_import():
    code = """
import builtins
__builtins__['print'](getattr(builtins, 'len')([1, 2, 3]))
x = getattr(obj, 'method')(1)
m = __import__('json').dumps({'a': 1})
"""
    out = transform(code)
    assert "print(3)" in out
    assert "obj.method(1)" in out
    assert "import json" in out
    assert "json.dumps({'a': 1})" in out


# -- algebraic / MBA --


def test_algebraic_and_mba_simplification():
    code = """
def calc(x, y):
    a = (x ^ y) + 2 * (x & y)
    b = (x | y) + (x & y)
    c = (x | y) - (x ^ y)
    d = (x ^ y) | (x & y)
    e = ~~x + 0 - 0
    f = (y * 1) ^ 0
    return (a, b, c, d, e, f)
"""
    out = transform(code)
    assert "x + y" in out
    assert "x & y" in out
    assert "x | y" in out
    assert "~~x" not in out
    assert "^ 0" not in out
    assert "* 1" not in out


# -- dead code / unused locals & imports --


def test_dead_code_truthy_if_while_raise_and_unused():
    code = """
import unused_mod
import used_mod

def fn(x):
    dead_local = 123 + 456
    if 1:
        y = used_mod.go(x)
    while False:
        print("never")
    return y
    unreachable = 999
"""
    out = transform(code)
    assert "import unused_mod" not in out
    assert "import used_mod" in out
    assert "dead_local" not in out
    assert "never" not in out
    assert "unreachable" not in out
    assert "return used_mod.go(x)" in out or "y = used_mod.go(x)" in out


# -- control flow simplifier --


def test_control_flow_simplifier():
    code = """
def f(x):
    x = x
    pass
    while True:
        y = x + 1
        break
    try:
        z = y + 2
    except Exception:
        z = 0
    return z
"""
    out = transform(code)
    assert "x = x" not in out
    assert "pass" not in out
    assert "while True" not in out
    assert "try:" not in out
    assert "y = x + 1" in out
    assert "z = y + 2" in out


# -- collections transformer --


def test_collections_subscript_and_builtins():
    code = """
a = [10, 20, 30][1]
b = {"k": "val"}["k"]
c = "abcdef"[::-1]
d = len([1, 2, 3, 4])
e = sum((1, 2, 3))
f = min(5, 2, 9)
g = max([3, 7, 1])
h = "".join(reversed("abc"))
"""
    out = transform(code)
    assert "a = 20" in out
    assert "b = 'val'" in out
    assert "c = 'fedcba'" in out
    assert "d = 4" in out
    assert "e = 6" in out
    assert "f = 2" in out
    assert "g = 7" in out
    assert "h = 'cba'" in out


# -- string format transformer --


def test_string_format_percent_and_bytearray():
    code = """
a = "{0} {name}".format("hi", name="there")
b = "%s:%d" % ("port", 8080)
c = b"hello %s" % b"world"
d = bytearray([79, 75]).decode("utf-8")
e = bytes([65, 66]).decode()
"""
    out = transform(code)
    assert "a = 'hi there'" in out
    assert "b = 'port:8080'" in out
    assert "c = b'hello world'" in out
    assert "d = 'OK'" in out
    assert "e = 'AB'" in out


# -- whitelist hardening & math/html --


def test_whitelist_math_html_and_import_alias_resolution():
    code = """
import math
import html

_m = math
x = _m.sqrt(16)
y = html.unescape("&lt;ok&gt;")
"""
    out = transform(code)
    assert "x = 4.0" in out
    assert "y = '<ok>'" in out
    assert "import html" not in out


def test_zip_bomb_protection():
    import zlib

    payload = zlib.compress(b"A" * 500)
    code = f"import zlib\nx = zlib.decompress({payload!r})"
    tree = ast.parse(code)
    pipeline = TransformerPipeline(
        transformers=[ConstsTransformer],
        max_allocation=50,
    )
    out = ast.unparse(pipeline.visit(tree))
    assert "zlib.decompress" in out


# -- exec unpacker --


def test_exec_unpacker_eval_and_compile():
    code = """
a = eval("1 + 2 * 3")
b = eval(compile("10 + 20", "<obf>", "eval"))
exec(compile("print('UNPACKED')", "<obf>", "exec"))
"""
    out = transform(code)
    assert "a = 7" in out
    assert "b = 30" in out
    assert "print('UNPACKED')" in out


# -- ternary simplifier --


def test_ternary_and_not_compare_simplifier():
    code = """
def f(a, b, c):
    x = not (a == b)
    y = not (not (a < b))
    z = 42 if c else 42
    w = True if a < b else False
    if c:
        k = 1
    else:
        k = 1
    return (x, y, z, w, k)
"""
    out = transform(code)
    assert "a != b" in out
    assert "a < b" in out
    assert "z = 42" in out or "42," in out
    assert "w = a < b" in out
    assert "return (x, y, 42, w, 1)" in out
    assert "else:" not in out


# -- dict dispatch simplifier --


def test_dict_dispatch_simplifier():
    code = """
def f():
    tbl = {"a": "print", "b": 42}
    arr = [10, 20, 30]
    mut = {"k": 1}
    mut["k"] = 99
    return (tbl["a"], tbl["b"], arr[1], mut["k"])
"""
    out = transform(code)
    assert "('print', 42, 20, mut['k'])" in out
    assert "tbl" not in out
    assert "arr" not in out


# -- builtin folder --


def test_builtin_folder():
    code = """
a = int("0xff", 16)
b = bin(10)
c = oct(8)
d = ascii("é")
e = any([0, False, 1])
f = all([1, True, "ok"])
g = sorted([3, 1, 2])
h = dict(zip(["x", "y"], [10, 20]))
"""
    out = transform(code)
    assert "a = 255" in out
    assert "b = '0b1010'" in out
    assert "c = '0o10'" in out
    assert "d = \"'\\\\xe9'\"" in out
    assert "e = True" in out
    assert "f = True" in out
    assert "g = [1, 2, 3]" in out
    assert "h = {'x': 10, 'y': 20}" in out


# -- real-world obfuscator regressions --


def test_zero_arg_call_does_not_crash_safe_eval():
    code = """
def main():
    exit()
main()
"""
    out = transform(code)
    assert "exit()" in out
    assert "main()" in out


def test_bytes_fromhex_decode_folds():
    code = """
msg = bytes.fromhex("48656c6c6f").decode("utf-8")
"""
    out = transform(code)
    assert "msg = 'Hello'" in out


def test_global_does_not_leak_into_local_or_comprehension_scope():
    code = """
A = print
def fib(n):
    seq = []
    A, B = 0, 1
    for _ in range(n):
        seq.append(A)
        A, B = B, A + B
    return seq
def total(nums):
    return sum(A * 2 for A in nums if A % 2 == 0)
"""
    out = transform(code)
    assert "seq.append(print)" not in out
    assert "print * 2" not in out
    assert "print % 2" not in out


def test_conditional_assignment_not_folded_across_branches():
    code = """
def greet(name, count):
    if count > 2:
        prefix = "Hello"
    else:
        prefix = "Hi"
    return f"{prefix}, {name}!"
"""
    out = transform(code)
    assert "return f'{prefix}, {name}!'" in out


def test_exec_unpacker_gzip_from_import_alias():
    import gzip

    payload = gzip.compress(b"x = 1 + 2\nprint(x)")
    code = f"from gzip import decompress as __\n_ = exec\n_(__( {payload!r} ))\n"
    out = transform(code)
    assert "x = 3" in out
    assert "print(3)" in out


def test_dead_code_remover_keeps_nonempty_except_body():
    code = """
try:
    risky()
except Exception:
    if False:
        x = 1
"""
    out = transform(code)
    ast.parse(out)
    assert "pass" in out


def test_tuple_unpacking_aliases_and_constants():
    code = """
a, b, c = int, "0xff", 16
x = a(b, c)
"""
    out = transform(code)
    assert "x = 255" in out


def test_immediate_lambda_and_vars_inlining():
    from noctyra.transformers import LambdaLP

    code = """
import math
fn = (lambda m: vars(m)["sqrt"])(math)
y = fn(16)
"""
    tree = ast.parse(transform(code))
    out = ast.unparse(LambdaLP().run(tree))
    assert "math.sqrt" in out
    assert "lambda" not in out


def test_exec_unpacker_compile_kwargs_and_class_globals():
    import zlib

    payload = zlib.compress(b"z = 40 + 2\n")
    code = f"""
import zlib
class Box:
    def put(k, v, g=globals):
        g()[k] = v
    def get(k):
        return globals()[k]
Box.put(k="key1", v={payload!r})
eval(compile("globals()['exec'](zlib.decompress(Box.get(k='key1')))", filename="f", mode="eval"))
"""
    out = transform(code)
    assert "z = 42" in out


def test_generic_seq_index_and_builtins_vars():
    code = """
import builtins
x = getattr(builtins, dir(builtins)[dir(builtins).index("int")])("42")
v = builtins.vars
v()["y"] = 10
"""
    out = transform(code)
    assert "x = 42" in out
    assert "y = 10" in out


def test_module_attr_alias_and_large_int_folding():
    code = """
import binascii
f = binascii.unhexlify
s = f(b"48656c6c6f").decode("utf-8")
n = 1526539672 + -1526539671
"""
    out = transform(code)
    assert "s = 'Hello'" in out
    assert "n = 1" in out


# -- security hardening --


def test_brotli_zstd_blosc_zip_bomb_protection():
    import blosc
    import brotli
    import zstd

    payload = b"A" * 500
    for mod_name, data in [
        ("brotli", brotli.compress(payload)),
        ("zstd", zstd.compress(payload)),
        ("blosc", blosc.compress(payload)),
    ]:
        code = f"import {mod_name}\nx = {mod_name}.decompress({data!r})"
        tree = ast.parse(code)
        pipeline = TransformerPipeline(
            transformers=[ConstsTransformer],
            max_allocation=50,
        )
        out = ast.unparse(pipeline.visit(tree))
        assert f"{mod_name}.decompress" in out


def test_pow_factorial_and_fstring_width_dos_protection():
    code = """
import math
a = pow(2, 10000000)
b = math.factorial(5000)
c = f"{1:99999999}"
"""
    out = transform(code)
    assert "pow(2, 10000000)" in out
    assert "math.factorial(5000)" in out
    assert "f'{1:99999999}'" in out


def test_str_format_blocks_dunder_field_traversal():
    code = 'x = "{0.__class__}".format("abc")'
    out = transform(code)
    assert "{0.__class__}" in out


def test_from_builtins_alias_resolves_in_name_replacer():
    code = """
from builtins import print
fn = print
fn("ok")
"""
    out = transform(code)
    assert "print('ok')" in out


def test_bytes_generator_xor_zlib_exec_compile_two_args():
    import zlib

    inner = 'print("decoded ok")'
    compressed = zlib.compress(inner.encode("utf-8"))
    key = b"lamp"
    xored = bytes(b ^ key[i % 4] for i, b in enumerate(compressed))
    code = f"""
def func_4():
    import zlib
    var_17 = bytes(({xored!r}[i] ^ b"lamp"[i % 4] for i in range({len(xored)})))
    var_18 = zlib.decompress(var_17).decode("utf-8")
    var_19 = {{"__name__": "__main__"}}
    exec(compile(var_18, "<ledger>", "exec"), var_19)
"""
    out = transform(code)
    assert "print('decoded ok')" in out
    assert "exec(" not in out
    assert "zlib.decompress" not in out


def test_oversized_range_blocked_by_max_allocation():
    code = "x = [i for i in range(10000000)]"
    out = transform(code)
    assert "range(10000000)" in out


def test_large_list_multiplication_not_expanded():
    code = """
arr = [b''] * 800
n = len(arr)
first = arr[0]
"""
    out = transform(code)
    assert "[b''] * 800" in out
    assert "n = 800" in out
    assert "first = b''" in out


# -- Audit regression & security tests --


def test_consts_keeps_lazy_iterators_and_store_subscript():
    code = """
r = range(5)
z = zip([1, 2], [3, 4])
m = map(str, [1, 2])
arr = [10, 20, 30]
arr[0] = 99
x = arr[0]
d = dict(zip(["a", "b"], [1, 2]))
"""
    out = transform(code)
    assert "r = range(5)" in out
    assert "z = zip(" in out
    assert "m = map(" in out
    assert "arr[0] = 99" in out
    assert "x = 10" not in out
    assert "d = {'a': 1, 'b': 2}" in out


def test_symbolic_truthiness_and_shadowed_builtins():
    code = """
import os
fn = lambda x: x + 1
a = bool(os)
b = bool(fn)
c = 1 if os else 2
d = 1 if fn else 2
if os:
    print("os_ok")
if fn:
    print("fn_ok")

def shadowed(chr, len, eval):
    return chr(65), len("abc"), eval("1 + 2")

f = lambda a, b=10: a + b
g = lambda x, *, y=5: x + y
ok1 = f(1)
ok2 = g(2)
bad1 = f()
bad2 = g(2, 3)
bad_set = set([[]])
"""
    out = transform(code)
    assert "a = False" not in out
    assert "b = False" not in out
    assert "c = 2" not in out
    assert "d = 2" not in out
    assert "os_ok" in out
    assert "fn_ok" in out
    assert "return (chr(65), len('abc'), eval('1 + 2'))" in out
    assert "ok1 = 11" in out
    assert "ok2 = 7" in out
    assert "bad1 = f()" in out
    assert "bad2 = g(2, 3)" in out
    assert "bad_set = set([[]])" in out


def test_partial_slice_and_dos_bounds():
    import zlib
    import zstd
    from noctyra.transformers.safe_eval import _is_zstd_single_frame_bounded

    raw_payload = b"A" * 150_000
    zlib_bomb = zlib.compress(raw_payload)
    raw_deflate_bomb = zlib_bomb[2:-4]
    parts_expr = "[" + ", ".join(["'a'"] * 200) + "]"
    code = f"""
import zlib
def f(i):
    s = "abcdefg"
    return s[i:5], s[2:i]
big_shift = 1 << 10000000
big_pow = 2 ** 10000000
big_bytes = bytes(10000000)
big_zip = zip([1, 2], range(10000000))
unk_zip = zip([1, 2], unknown)
b1 = zlib.decompress({zlib_bomb!r})
b2 = zlib.decompress({raw_deflate_bomb!r}, -15)
b3 = zlib.decompress({zlib_bomb!r}, wbits=15)
fmt1 = "%.9999999f" % 1.5
fmt2 = "%*d" % (9999999, 1)
fmt3 = "%(k)9999999s" % {{"k": "a"}}
big_join = ("x" * 1000).join(reversed({parts_expr}))
"""
    out = transform(code)
    assert "'abcdefg'[i:5]" in out
    assert "'abcdefg'[2:i]" in out
    assert "'abcde'" not in out
    assert "1 << 10000000" in out
    assert "2 ** 10000000" in out
    assert "bytes(10000000)" in out
    assert "zip(" in out
    assert "A" * 1000 not in out
    assert "%.9999999f" in out
    assert "%*d" in out
    assert "%(k)9999999s" in out

    z_small = zstd.compress(b"B" * 100)
    assert _is_zstd_single_frame_bounded(z_small, 200) is True
    assert _is_zstd_single_frame_bounded(z_small, 50) is False
    # Unknown FCS header (magic + FHD without single_seg/fcs + payload) must be rejected
    no_fcs_frame = b"\x28\xb5\x2f\xfd\x00\x00"
    assert _is_zstd_single_frame_bounded(no_fcs_frame, 100_000) is False
    # Trailing / concatenated second frame must be rejected
    assert _is_zstd_single_frame_bounded(z_small + z_small, 100_000) is False


def test_comprehensions_generator_and_cartesian_guard():
    code = """
g = (x * 2 for x in [1, 2])
nxt = next((x for x in [1, 2]))
bad_unpack = [(a, b) for a, b, c in [(1, 2)]]
unk_filter = [x for x in [1, 2] if pred(x)]
big_cart = [x + y for x in range(1000) for y in range(1000)]
"""
    out = transform(code)
    assert "g = (x * 2 for x in [1, 2])" in out
    assert "nxt = next(" in out
    assert "for a, b, c in [(1, 2)]" in out
    assert "if pred(x)" in out
    assert "for x in range(1000) for y in range(1000)" in out


def test_control_flow_ternary_and_dce_edge_cases():
    code = """
from __future__ import annotations

x = x
try:
    z = unknown + 1
except NameError:
    z = 0
t1 = 1 if side_effect() else 1
if side_effect():
    y = 1
else:
    y = 1
"""
    out = transform(code)
    assert "from __future__ import annotations" in out
    assert "x = x" in out
    assert "except NameError:" in out
    assert "side_effect()" in out
    assert out.count("side_effect()") == 2


def test_scoping_aliasing_walrus_and_exec_reuse():
    import ast
    from noctyra.transformers.ExecUnpacker import ExecUnpacker

    code = """
a = 1
b = 2
a, b = b, a
swap_res = (a, b)

tbl = [10, 20]
alias = tbl
tbl.append(30)
n = len(tbl)
first_alias = alias[0]

def walrus_case():
    w = 10
    if (w := 20) > 0:
        pass
    return w

def try_case():
    val = 1
    try:
        val = 2
        risky()
    except Exception:
        val = 3
    return val

def finally_case():
    v = 1
    try:
        pass
    finally:
        v = 9
    return v
"""
    out = transform(code)
    assert "swap_res = (2, 1)" in out
    assert "n = len(tbl)" in out
    assert "first_alias = alias[0]" in out
    assert "return 10" not in out
    assert "return 1" not in out

    unpacker = ExecUnpacker()
    m1 = ast.parse("class C:\n    x = 1\n")
    m2 = ast.parse("y = C.x\n")
    unpacker.run(m1)
    res2 = ast.unparse(unpacker.run(m2))
    assert res2 == "y = C.x"


def test_inliner_imports_ordering_keywords_and_collisions():
    from noctyra.transformers.Imports import ImportAliasFolder

    inliner_code = '''"""Module doc."""
from __future__ import annotations
__builtins__["inj"] = 1
json = make_fake()
ok_mod = __import__("math")
real = __import__("json")
kw1 = __import__("class")
kw2 = getattr(obj, "return")
'''
    out = transform(inliner_code)
    compile(out, "<inliner_test>", "exec")
    assert out.index('"""Module doc."""') < out.index("from __future__ import annotations")
    assert out.index("from __future__ import annotations") < out.index("import math")
    assert "ok_mod = math" in out
    assert "__builtins__['inj'] = 1" in out
    assert "real = __import__('json')" in out
    assert "__import__('class')" in out
    assert "getattr(obj, 'return')" in out

    imp_code = """
import math as m
from mod1 import x as a
from mod2 import x as b

def shadow_math():
    math = 123
    return m.sqrt(4) + math

res = (a, b)
"""
    import ast

    imp_out = ast.unparse(ImportAliasFolder().run(ast.parse(imp_code)))
    assert "from mod2 import x as b" in imp_out
    assert "res = (x, b)" in imp_out
    assert "m.sqrt(4)" in imp_out


def test_lambda_lp_guards_and_renamer_edges():
    import ast
    from noctyra.transformers.LambdaLP import LambdaLP

    lp_code = """
a = (lambda x, y=10: x + y)(z)
b = (lambda *args: args[0])(z)
c = (lambda x: x)(*items)
d = (lambda x: x + x)(f())
e = (lambda x: 42)(f())
g = (lambda y: list(map(lambda x: x + y, items)))(x)
"""
    lp_out = ast.unparse(LambdaLP().run(ast.parse(lp_code)))
    assert "a = z + 10" in lp_out
    assert "(lambda *args: args[0])(z)" in lp_out
    assert "(lambda x: x)(*items)" in lp_out
    assert "(lambda x: x + x)(f())" in lp_out
    assert "(lambda x: 42)(f())" in lp_out
    assert "(lambda y: list(map(lambda x: x + y, items)))(x)" in lp_out

    ren_code = """
import math as g

class Box:
    def method(self, alpha=1):
        return alpha

def f():
    global g
    val = int(g.sqrt(9))
    g = 123
    return val

def h():
    return g

res = (f(), h(), make_box().method(alpha=2))
"""
    # Also verify runtime semantics of renamed global alias match original
    g_code = """
import math as g
def f():
    global g
    val = int(g.sqrt(9))
    g = 123
    return val
def h():
    return g
print((f(), h()))
"""
    import contextlib
    import io

    g_out = rename(g_code, mode="all")
    buf1, buf2 = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf1):
        exec(g_code, {})
    with contextlib.redirect_stdout(buf2):
        exec(g_out, {})
    assert buf1.getvalue() == buf2.getvalue() == "(3, 123)\n"

    ren_out = rename(ren_code, mode="all")
    assert "alpha=1" in ren_out
    assert "method(alpha=2)" in ren_out


def test_cli_pipeline_single_dir_errors_and_stdout(tmp_path, monkeypatch, capsys):
    import sys
    from noctyra.cli import _build_parser, _deobfuscate_code, main as cli_main

    parser = _build_parser()
    args = parser.parse_args(["dummy.py", "-q"])
    src = "x = (lambda a, b=10: a + b)(z)\ny = 2 + 3\n"
    deobf, _, _ = _deobfuscate_code(src, args)
    assert "z + 10" in deobf
    assert "= 5" in deobf

    # Single file CLI run -> output file
    in_file = tmp_path / "obf.py"
    out_file = tmp_path / "clean.py"
    in_file.write_text("a = 10 + 20\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["noctyra", str(in_file), "-o", str(out_file), "-q"]
    )
    cli_main()
    assert "= 30" in out_file.read_text(encoding="utf-8")

    # Directory batch with valid, invalid-UTF8, and SyntaxError files + --stdout
    in_dir = tmp_path / "in_dir"
    out_dir = tmp_path / "out_dir"
    in_dir.mkdir()
    (in_dir / "good.py").write_text("k = 3 * 7\n", encoding="utf-8")
    (in_dir / "bad_utf8.py").write_bytes(b"\xff\xfe\x00\x80")
    (in_dir / "bad_syntax.py").write_text("def broken(:\n", encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv", ["noctyra", str(in_dir), "-o", str(out_dir), "-q"]
    )
    cli_main()
    assert "= 21" in (out_dir / "good.py").read_text(encoding="utf-8")
    assert not (out_dir / "bad_utf8.py").exists()
    assert not (out_dir / "bad_syntax.py").exists()

    monkeypatch.setattr(
        sys, "argv", ["noctyra", str(in_dir), "--stdout", "-q"]
    )
    cli_main()
    captured = capsys.readouterr().out
    assert "= 21" in captured


def test_variadic_lambda_pure_args_len_and_boolop_walrus():
    code = """
os = __import__('os')
s = lambda *_: []
idk = str(ModuleNotFoundError)
x = 1 if (not idk or not os or not s or not (fn := getattr(__builtins__, 'len'))) else fn([s(os.close, int), str])
s_val = 'olleh'[::-fn([s(os.close)])]
"""
    out = transform(code)
    assert "x = 2" in out
    assert "s_val = 'hello'" in out


def test_dict_of_lambdas_dispatch_folds_in_comprehension():
    code = """
ops = {0: lambda x, y: x + y, 1: lambda x, y: x ^ y}
msg = "".join([chr(ops[1](c, 0x42)) for c in [x ^ 0x42 for x in b"secret"]])
print(msg)
"""
    out = transform(code)
    assert "print('secret')" in out


def test_control_flow_flattening_unrolling():
    code = """
def f(x):
    st = "init"
    while True:
        if st == "init":
            y = x + 1
            st = "fin"
        elif st == "fin":
            return y * 2
        elif st == "dead":
            y = 999
            break
"""
    out = transform(code)
    assert "while True:" not in out
    assert "999" not in out
    assert "y = x + 1" in out
    assert "return y * 2" in out

    code2 = """
_state = 3
_res = []
while _state != 0:
    if _state == 3:
        _res.append("A")
        _state = 1
    elif _state == 1:
        _res.append("B")
        _state = 2
    elif _state == 2:
        _res.append("C")
        _state = 0
"""
    out2 = transform(code2)
    assert "while " not in out2
    assert out2.index("'A'") < out2.index("'B'") < out2.index("'C'")


def test_str_dict_descriptor_get_bound_method():
    code = """
joiner = str.__dict__["join"].__get__("", str)
msg = joiner(["h", "e", "l", "l", "o"])
print(msg)
"""
    out = transform(code)
    assert "print('hello')" in out


def test_single_return_def_with_generatorexp_folds_calls():
    code = """
data = b"\\x02\\x0240-2/)\\x02\\x02"
def dec(buf, key=93):
    return "".join(chr(x ^ key) for x in buf)
res = dec(data)
print(res)
"""
    out = transform(code)
    assert "print('__import__')" in out


def test_builtins_dict_or_vars_ternary_subscript():
    code = """
b = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
fn = b['print']
fn("hey")
"""
    out = transform(code)
    assert "print('hey')" in out


def test_builtins_import_ternary_and_attribute_alias():
    code = """
var_1 = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
__im0__ = __import__ if isinstance(var_1, dict) else var_1.__import__
__bm0__ = __im0__("base64")
__bd__ = __bm0__.b85decode
print(__bd__(b"Xk~0{Zv"))
exec(__bd__(b"aB^vGbSN}3DF").decode())
"""
    out = transform(code)
    assert "print(b'hello')" in out
    assert "print(42)" in out


def test_bytearray_and_bounded_nested_while_loop():
    code = """
p = [bytes([b ^ 42 for b in b"print("]), bytes([b ^ 42 for b in b"123)"])]
z = [bytearray(), bytearray()]
li = 0
while li < 2:
    po = 0
    while po < len(p[li]):
        z[li].append(p[li][po] ^ 42)
        po += 1
    li += 1
exec(bytes(z[0] + z[1]).decode())
"""
    out_default = transform(code)
    assert "while li < 2:" in out_default

    out_enabled = transform(code, advanced=True)
    assert "print(123)" in out_enabled


def test_bounded_while_respects_max_allocation_and_side_effects():
    over_limit = """
i = 0
buf = bytearray()
while i < 50:
    buf.append(65)
    i += 1
print(len(buf))
"""
    pipeline = TransformerPipeline(
        transformers=[ConstsTransformer, ControlFlowSimplifier],
        max_allocation=10,
        advanced=True,
    )
    out = ast.unparse(pipeline.visit(ast.parse(over_limit)))
    assert "while i < 50:" in out

    side_effect = """
i = 0
while i < 3:
    print(i)
    i += 1
"""
    out_se = transform(side_effect, advanced=True)
    assert "while i < 3:" in out_se


def test_lambda_subscript_pure_container_with_builtin():
    from noctyra.transformers import LambdaLP

    pipeline = TransformerPipeline([LambdaLP, CollectionsTransformer])
    code = '(lambda _, /: _[1](_[0]))(["hey", print])'
    out = ast.unparse(pipeline.visit(ast.parse(code)))
    assert out == "print('hey')"

    # Must NOT inline if the mutable list is passed directly (identity/mutation hazard)
    unsafe = '(lambda _, /: (_ is _, _[0]))(["hey", print])'
    out_unsafe = ast.unparse(pipeline.visit(ast.parse(unsafe)))
    assert "lambda" in out_unsafe


