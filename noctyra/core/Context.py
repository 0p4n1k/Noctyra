from .Variable import Variable


class Context:
    def __init__(self, _vars=None, parent=None):
        self.vars: list[Variable] = _vars or []
        self.invalidated: list[str] = []
        self.remapped_funcs: dict[str, str] = {}
        self.import_aliases: dict[str, str] = {}
        self.parent = parent

    def get(self, name: str):
        for var in reversed(self.vars):  # Respect shadowing
            if var.name == name and var.has_value():
                return var

        if name in self.invalidated:
            return None

        if self.parent:
            return self.parent.get(name)

        return None

    def has(self, name: str):
        return self.get(name) is not None

    def set(self, name: str, value):
        if name in self.invalidated:
            self.invalidated = [n for n in self.invalidated if n != name]
        self.remapped_funcs.pop(name, None)

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
        if name not in self.invalidated:
            self.invalidated.append(name)
        self.vars = [v for v in self.vars if v.name != name]
        self.remapped_funcs.pop(name, None)

    def remap(self, name: str, target: str):
        if name in self.invalidated:
            self.invalidated = [n for n in self.invalidated if n != name]
        self.vars = [v for v in self.vars if v.name != name]
        self.remapped_funcs[name] = target

    def remap_get(self, name: str) -> str | None:
        if value := self.remapped_funcs.get(name):
            return value

        if name in self.invalidated or any(
            v.name == name and v.has_value() for v in self.vars
        ):
            return None

        if self.parent:
            return self.parent.remap_get(name)

        return None

    def remap_is(self, name: str, targets: list[str]) -> bool:
        if name in self.remapped_funcs:
            return self.remapped_funcs[name] in targets

        if name in self.invalidated or any(
            v.name == name and v.has_value() for v in self.vars
        ):
            return False

        if self.parent:
            return self.parent.remap_is(name, targets)

        return name in targets

    def set_import_alias(self, module: str, alias: str) -> None:
        self.import_aliases[module] = alias

    def get_import_alias(self, module: str) -> str | None:
        if module in self.import_aliases:
            return self.import_aliases[module]
        if self.parent:
            return self.parent.get_import_alias(module)
        return None
