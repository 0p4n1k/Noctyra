from typing import Generic, TypeVar
from noctyra.core.Symbolic import SymbolicValue
from .Symbolic import LambdaType

supported_types = (
    int | float | str | bool | bytes | list | dict | set | LambdaType | SymbolicValue
)
supported_iterator = str | bytes | dict | list | set


T = TypeVar("T", bound=supported_types | SymbolicValue)


class Variable(Generic[T]):
    def __init__(self, name: str, value: T):
        self.name = name
        self.value: T = value

    def has_value(self):
        return self.value is not None

    def set(self, *, value: T):
        self.value = value

    def get(self) -> T:
        return self.value

    def __repr__(self):
        return f"Variable(name={self.name}, value={self.value})"
