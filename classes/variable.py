supported_types = int | float | str | bool | bytes | list | dict | set


class Variable:
    def __init__(self, name, value):

        if not isinstance(name, str):
            raise ValueError(f"Variable name must be a string. {name=}, {value=}")

        if not isinstance(value, supported_types):
            raise ValueError(f"Unsupported variable type. {name=}, {value=}")

        self.name = name
        self.value = value

    def has_value(self):
        return self.value is not None

    def set(self, *, value):

        if not isinstance(value, supported_types) and value is not None:
            raise ValueError(
                f"Unsupported variable type: {type(value).__name__}. {self.name=}, {value=}"
            )

        self.value = value

    def get(self) -> supported_types:
        return self.value

    def __repr__(self):
        return f"Variable(name={self.name}, value={self.value})"
