from noctyra.core.Transformer import BaseTransformer
import ast


class BasicInliner(BaseTransformer):
    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:

        if isinstance(node.value, ast.Call):
            if (
                isinstance(node.value.func, ast.Name)
                and self.ctx.remap_is(node.value.func.id, ["globals", "locals"])
                and self.ctx.is_usable(node.value.func.id)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
                and node.slice.value.isidentifier()
            ):

                return ast.copy_location(ast.Name(node.slice.value, ctx=node.ctx), node)

        return node
