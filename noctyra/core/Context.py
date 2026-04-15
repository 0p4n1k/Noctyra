from .Variable import Variable


class Context:
    def __init__(self, _vars=None, parent=None):
        self.vars: list[Variable] = _vars or []
        self.invalidated: list[str] = []
        self.remapped_funcs: dict[str, str] = {}
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

    def is_usable(self, name: str) -> bool:
        if name in self.invalidated:
            return False

        if self.parent:
            return self.parent.is_usable(name)

        return True

    def invalidate(self, name: str) -> None:
        self.invalidated.append(name)
        self.vars = [v for v in self.vars if v.name != name]

    def remap(self, name: str, target: str):
        self.remapped_funcs[name] = target

    def remap_get(self, name: str) -> str | None:
        if value := self.remapped_funcs.get(name):
            return value

        if self.parent:
            return self.parent.remap_get(name)

        return None

    def remap_is(self, name: str, targets: list[str]) -> bool:

        if self.remapped_funcs.get(name) in targets:
            return True

        if self.parent:
            return self.parent.remap_is(name, targets)

        return name in targets
