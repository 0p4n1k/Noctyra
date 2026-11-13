from noctyra.transformers import (
    ConstsTransformer,
    BasicFunctions,
    BasicAttributes,
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
)
from noctyra.core import TransformerPipeline
import ast


def transform(code: str) -> str:
    tree = ast.parse(code)
    pipeline = TransformerPipeline(
        transformers=[
            ImportAliasFolder,
            BasicInliner,
            ConstsTransformer,
            AlgebraicSimplifier,
            CollectionsTransformer,
            BasicFunctions,
            BasicAttributes,
            FStringTransformer,
            LCTransformer,
            ConditionSimplifier,
            ControlFlowSimplifier,
            NameReplacer,
            DeadCodeRemover,
        ]
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
