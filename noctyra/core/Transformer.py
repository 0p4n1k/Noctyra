from noctyra.transformers.safe_eval import safe_eval
from noctyra.core import Context
import ast


class BaseTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.ctx: Context = Context()

    def run(
        self,
        node: ast.AST,
        ctx: Context,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ) -> ast.AST:
        self.ctx = ctx
        self.max_depth = max_depth
        self.max_allocation = max_allocation
        return self.visit(node)

    def eval(self, node: ast.expr, ctx: Context | None = None):
        return safe_eval(
            node,
            ctx=ctx or self.ctx,
            max_depth=self.max_depth,
            max_allocation=self.max_allocation,
        )

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

    def visit_ClassDef(self, node: ast.ClassDef):
        parent_ctx = self.ctx

        self.ctx = Context.from_tree(node)
        self.generic_visit(node)

        self.ctx = parent_ctx
        return node
