"""
AI Generated Test Cases for Transformers
"""

from transformers import (
    TransformerPipeline,
    ConstsTransformer,
    BasicFunctions,
    BasicAttributes,
    LCTransformer,
    ConditionSimplifier,
)
import ast


def transform_code(code: str) -> str:
    tree = ast.parse(code)
    pipeline = TransformerPipeline(
        transformers=[
            ConstsTransformer,
            BasicFunctions,
            BasicAttributes,
            LCTransformer,
            ConditionSimplifier,
        ]
    )
    result = pipeline.visit(tree)
    return ast.unparse(result)


def test_const_folding():
    code = "x = 1 + 2 * 3"
    transformed = transform_code(code)
    assert "x = 7" in transformed


def test_base64_decode():
    code = "import base64; x = base64.b64decode('SGVsbG8=').decode()"
    transformed = transform_code(code)
    assert "x = 'Hello'" in transformed


def test_exec_unrolling():
    code = "exec('print(\"unrolled\")')"
    transformed = transform_code(code)

    assert "print('unrolled')" in transformed or 'print("unrolled")' in transformed
    assert "exec" not in transformed


def test_list_comp_folding():
    code = "x = [i * 2 for i in [1, 2, 3] if i > 1]"
    transformed = transform_code(code)
    assert "x = [4, 6]" in transformed


def test_condition_simplification():
    code = "if 1 < 2 < 3: pass"
    transformed = transform_code(code)
    assert "if True: pass" in transformed or "if True:\n    pass" in transformed


def test_safe_eval_limits():
    # Large allocation should NOT be folded
    code = "x = 'A' * 10**8"  # Increased to be sure it hits limit
    transformed = transform_code(code)
    assert "10**8" in transformed or "100000000" in transformed
    # If it was folded, transformed would be > 100MB.
    # Since it's NOT folded, it stays small.
    assert len(transformed) < 1000
