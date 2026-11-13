from noctyra.core.Transformer import BaseTransformer
from noctyra.core import LambdaType, ImportSymbol
from noctyra.utils import LOGGER
import ast

from noctyra.utils import IMMUTABLE_TYPES


class NameReplacer(BaseTransformer):
    def visit_Import(self, node: ast.Import) -> ast.AST:
        super().visit_Import(node)
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            if alias.asname:
                self.ctx.set_import_alias(alias.name, bound)
            else:
                self.ctx.set_import_alias(alias.name.split(".")[0], bound)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        super().visit_ImportFrom(node)
        if node.module:
            for alias in node.names:
                if alias.name != "*":
                    bound = alias.asname or alias.name
                    self.ctx.set_import_alias(f"{node.module}.{alias.name}", bound)
        return node

    def visit_Name(self, node):
        self.generic_visit(node)

        if not isinstance(node.ctx, ast.Load):
            return node

        result_res = self.eval(node)
        if result_res is not None:
            if isinstance(result_res, ImportSymbol):
                target_name = (
                    self.ctx.get_import_alias(result_res.module) or result_res.module
                )
                if target_name.isidentifier() and target_name != node.id:
                    target_var = self.ctx.get(target_name)
                    if (
                        self.ctx.is_usable(target_name)
                        and self.ctx.remap_get(target_name) is None
                        and target_var is not None
                        and isinstance(target_var.get(), ImportSymbol)
                        and target_var.get().module == result_res.module
                    ):
                        LOGGER.debug(
                            f"Resolved import alias: {node.id} -> {target_name}"
                        )
                        return ast.copy_location(
                            ast.Name(id=target_name, ctx=node.ctx), node
                        )
                if "." in result_res.module:
                    mod, attr = result_res.module.rsplit(".", 1)
                    if (
                        mod in ("builtins", "__builtins__")
                        and attr.isidentifier()
                        and attr != node.id
                        and self._is_builtin_usable(attr)
                    ):
                        LOGGER.debug(f"Resolved builtin alias: {node.id} -> {attr}")
                        return ast.copy_location(
                            ast.Name(id=attr, ctx=node.ctx), node
                        )
            result = self.unwrap(result_res)
            if not isinstance(result_res, (LambdaType, ImportSymbol)) and isinstance(
                result, IMMUTABLE_TYPES
            ):
                LOGGER.debug(f"Resolved variable: {node.id} -> {result!r}")
                return ast.Constant(value=result)

        if value := self.ctx.remap_get(node.id):
            return ast.copy_location(ast.Name(value, ctx=node.ctx), node)

        return node
