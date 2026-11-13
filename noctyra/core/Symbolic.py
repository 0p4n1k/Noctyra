from typing import Generic, TypeVar, Any, Optional
import copy
import ast
import math

T = TypeVar("T")


class SymbolicValue(Generic[T]):
    def __init__(self, value: T, **metadata: Any) -> None:
        self.value = value
        self.metadata = metadata

    def __repr__(self):
        return f"Symbolic({self.value!r}, meta={self.metadata})"

    def to_ast(self) -> ast.AST:
        if "custom_ast" in self.metadata:
            return self.metadata["custom_ast"]

        return ast.Constant(value=self.value)  # type: ignore


class NoneValue(SymbolicValue[None]):
    def __init__(self) -> None:
        super().__init__(None)


class ImportSymbol(SymbolicValue[None]):
    def __init__(self, module: str, member: str | None = None) -> None:
        super().__init__(None, _type="_import")
        self.module = module
        self.member = member


class LambdaType(SymbolicValue[None]):
    def __init__(self, body: ast.AST, args: ast.arguments) -> None:
        super().__init__(value=None)

        self.body = copy.deepcopy(body)
        self.args = copy.deepcopy(args)

    def to_ast(self):
        return ast.Lambda(
            body=copy.deepcopy(self.body), args=copy.deepcopy(self.args)  # type: ignore
        )

    def get_args(self):
        return self.args

    def get_body(self) -> ast.AST:
        return copy.deepcopy(self.body)


def is_symbolic_ref(obj: Any) -> bool:
    """Return True if obj or any nested element is a symbolic callable/import."""
    if isinstance(obj, (ImportSymbol, LambdaType)):
        return True
    if isinstance(obj, SymbolicValue):
        return is_symbolic_ref(obj.value)
    if isinstance(obj, (list, tuple, set)):
        return any(is_symbolic_ref(x) for x in obj)
    if isinstance(obj, dict):
        return any(is_symbolic_ref(k) or is_symbolic_ref(v) for k, v in obj.items())
    return False


def unwrap(obj: Any) -> Any:
    """Unwrap SymbolicValue wrappers while preserving ImportSymbol and LambdaType."""
    if isinstance(obj, (ImportSymbol, LambdaType)):
        return obj
    if isinstance(obj, SymbolicValue):
        return unwrap(obj.value)
    if isinstance(obj, list):
        return [unwrap(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(unwrap(x) for x in obj)
    if isinstance(obj, set):
        return {unwrap(x) for x in obj}
    if isinstance(obj, dict):
        return {unwrap(k): unwrap(v) for k, v in obj.items()}
    return obj


def to_node(value: Any) -> Optional[ast.expr]:
    """Convert an evaluated constant or literal container to an AST expression."""
    if isinstance(value, (ImportSymbol, LambdaType)):
        return None
    if isinstance(value, SymbolicValue):
        return to_node(value.value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return ast.Constant(value=value)
    if isinstance(value, list):
        elts = [to_node(x) for x in value]
        if any(e is None for e in elts):
            return None
        return ast.List(elts=[e for e in elts if e is not None], ctx=ast.Load())
    if isinstance(value, tuple):
        elts = [to_node(x) for x in value]
        if any(e is None for e in elts):
            return None
        return ast.Tuple(elts=[e for e in elts if e is not None], ctx=ast.Load())
    if isinstance(value, set):
        elts = [to_node(x) for x in value]
        if any(e is None for e in elts):
            return None
        return ast.Set(elts=[e for e in elts if e is not None])
    if isinstance(value, dict):
        keys: list[Optional[ast.expr]] = []
        vals: list[ast.expr] = []
        for k, v in value.items():
            kn = to_node(k)
            vn = to_node(v)
            if kn is None or vn is None:
                return None
            keys.append(kn)
            vals.append(vn)
        return ast.Dict(keys=keys, values=vals)
    return None
