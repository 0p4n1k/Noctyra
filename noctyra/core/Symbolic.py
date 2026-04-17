from typing import Generic, TypeVar, Any, Optional
import copy
import ast

T = TypeVar("T")


class SymbolicValue(Generic[T]):
    def __init__(
        self, value: T, origin_node: Optional[ast.AST] = None, **metadata
    ) -> None:
        self.value = value
        self.origin_node = origin_node
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
        super().__init__(None, _type = '_import')
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

    def __call__(self, evaluator, *args: Any, **kwargs: Any) -> Any:
        return evaluator.exec_custom_func(self, args, kwargs)
