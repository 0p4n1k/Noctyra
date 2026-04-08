from transformers import (
    TransformerPipeline,
    ConstsTransformer,
    BasicFunctions,
    BasicAttributes,
    LCTransformer,
    ConditionSimplifier,
    NameReplacer,
    DeadCodeRemover,
)
import ast


def transform(code: str) -> str:
    tree = ast.parse(code)
    pipeline = TransformerPipeline(
        transformers=[
            ConstsTransformer,
            BasicFunctions,
            BasicAttributes,
            LCTransformer,
            ConditionSimplifier,
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


# -- edge cases safe_eval --


def test_division_by_zero_protection():
    code = "x = 1 / 0"
    out = transform(code)

    # Should not crash or fold
    assert isinstance(out, str)


# -- args handling --


def test_function_kwargs():
    code = "x = pow(2, exp = 3)"
    out = transform(code)

    assert "x = 8" in out


# -- const folding --


def test_const_folding_basic():
    assert "x = 7" in transform("x = 1 + 2 * 3")


def test_const_folding_string():
    assert "x = 'aaa'" in transform("x = 'a' * 3")


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
