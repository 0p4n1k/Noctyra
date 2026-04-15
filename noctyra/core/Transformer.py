from noctyra.core.Function import CustomFunction
from noctyra.transformers.safe_eval import safe_eval
from noctyra.core import Context
import ast



class BaseTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.ctx: Context = Context()

    def run(
        self,
        node: ast.AST,
        ctx: Context | None = None,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ) -> ast.AST:

        self.ctx = ctx or Context()
        self.max_depth = max_depth
        self.max_allocation = max_allocation
        return self.visit(node)

    def eval(self, node: ast.AST | None, ctx: Context | None = None):
        return safe_eval(
            node,
            ctx=ctx or self.ctx,
            max_depth=self.max_depth,
            max_allocation=self.max_allocation,
        )

    def _def_visit(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        old_ctx = self.ctx

        self.ctx = Context(parent=old_ctx)

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for arg in node.args.args:
                self.ctx.invalidate(arg.arg)

        result = self.generic_visit(node)

        self.ctx = old_ctx
        return result

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)

        try:
            value = self.eval(node.value)

            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Lambda):
                        self.ctx.set(
                            target.id, CustomFunction(node.value.body, node.value.args)
                        )

                    elif value is not None:
                        self.ctx.set(target.id, value)

                    elif isinstance(node.value, ast.Name):
                        self.ctx.remap(target.id, node.value.id)

        except Exception:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.ctx.invalidate(target.id)

        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        return self._def_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self._def_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        return self._def_visit(node)
