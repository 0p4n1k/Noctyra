from transformers.safe_eval import safe_eval
from classes import Context
import ast


class BaseTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.ctx: Context = Context()

    def run(self, node: ast.AST, ctx: Context) -> ast.AST:
        self.ctx = ctx
        return self.visit(node)

    def eval(self, node: ast.expr, ctx: Context | None = None):
        return safe_eval(node, ctx=ctx or self.ctx)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        parent_ctx = self.ctx

        self.ctx = Context.from_tree(node)
        self.generic_visit(node)

        self.ctx = parent_ctx
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        parent_ctx = self.ctx

        self.ctx = Context.from_tree(node)
        self.generic_visit(node)

        self.ctx = parent_ctx
        return node
