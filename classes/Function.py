import ast


class CustomFunction:
    def __init__(self, body: ast.AST, args: ast.arguments) -> None:
        self.body = body
        self.args = args
