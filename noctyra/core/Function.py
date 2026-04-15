import ast
import copy


class CustomFunction:
    def __init__(self, body: ast.AST, args: ast.arguments) -> None:
        self.body = copy.deepcopy(body)
        self.args = copy.deepcopy(args)

    def get_body(self):
        return copy.deepcopy(self.body)

    def get_args(self):
        return copy.deepcopy(self.args)
