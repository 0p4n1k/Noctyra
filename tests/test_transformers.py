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


# -- const folding --


def test_const_folding_basic():
    assert "x = 7" in transform("x = 1 + 2 * 3")


def test_const_folding_string():
    assert "x = 'aaa'" in transform("x = 'a' * 3")


def test_safe_eval_limit():
    # Shouldn't fold to a huge string
    out = transform("x = 'A' * 10**8")
    assert len(out) < 1000


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
