from .Variable import Variable


class Context:
    def __init__(self, _vars=None, parent=None):
        self.vars: list[Variable] = _vars or []
        self.parent = parent

    def get(self, name: str):
        for var in reversed(self.vars):  # Respect shadowing
            if var.name == name and var.has_value():
                return var

        if self.parent:
            return self.parent.get(name)

        return None

    def has(self, name: str):
        return self.get(name) is not None

    def set(self, name: str, value):

        for var in self.vars:
            if var.name == name:
                var.set(value=value)
                return

        self.vars.append(Variable(name=name, value=value))

    def invalidate(self, name: str) -> None:
        self.vars = [v for v in self.vars if v.name != name]
