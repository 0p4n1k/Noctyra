from classes.variable import Variable
import ast


class Context:
    def __init__(self, vars=None):
        self.vars: list[Variable] = vars or []

    def get(self, name: str):
        for var in self.vars:
            if var.name == name and var.has_value():
                return var

        return None

    def has(self, name: str):
        return any(var.name == name for var in self.vars)

    def set(self, name: str, value):

        for var in self.vars:
            if var.name == name:
                var.set(value=value)
                return

        self.vars.append(Variable(name=name, value=value))

    def copy_with(self, vars: list[Variable]):
        new = Context(vars=self.vars.copy())
        new.vars.extend(vars)
        return new

    def invalidate(self, name: str) -> None:
        self.vars = [v for v in self.vars if v.name != name]

    @staticmethod
    def from_tree(tree: ast.AST) -> "Context":
        ctx = Context()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                try:
                    if node.value is None:
                        continue
                    targets = (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    )

                    if not all(isinstance(t, ast.Name) for t in targets):
                        continue

                    value = ast.literal_eval(node.value)
                    if isinstance(
                        value, (int, float, str, bool, bytes, list, dict, set)
                    ):
                        for target in targets:
                            if isinstance(target, ast.Name):
                                ctx.set(target.id, value)
                except ValueError:
                    pass

            elif isinstance(node, ast.AugAssign):
                if not isinstance(node.target, ast.Name):
                    continue

                ctx.invalidate(node.target.id)

        return ctx
