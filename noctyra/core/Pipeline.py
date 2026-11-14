from noctyra.utils import LOGGER
from typing import Sequence, Type
import ast


class TransformerPipeline(ast.NodeTransformer):
    def __init__(
        self,
        transformers: Sequence[Type[ast.NodeTransformer] | ast.NodeTransformer],
        iterations: int = 0,
        max_iterations: int = 100,
        max_depth: int = 50,
        max_allocation: int = 100_000,
        advanced: bool = False,
    ):
        self.transformers = [
            t() if isinstance(t, type) else t for t in transformers
        ]
        if advanced:
            for t in self.transformers:
                if hasattr(t, "advanced"):
                    setattr(t, "advanced", True)
        self.iterations = iterations
        self.max_iterations = max_iterations
        self.max_allocation = max_allocation
        self.max_depth = max_depth
        self.advanced = advanced
        LOGGER.info(
            f"Initialized TransformerPipeline with {len(self.transformers)} transformers and {self.iterations if self.iterations > 0 else 'auto'} iterations."
        )

    def run_transformer(
        self, transformer: ast.NodeTransformer, node: ast.AST
    ) -> ast.AST:

        return getattr(
            transformer,
            "run",
            (lambda node, ctx, max_depth, max_allocation: transformer.visit(node)),
        )(node, None, self.max_depth, self.max_allocation)

    def visit(self, node):

        current_node = node

        if self.iterations == 0:
            last_dump = ast.dump(current_node)
            cur = 1
            while True:
                for transformer in self.transformers:
                    new_node = self.run_transformer(transformer, current_node)

                    if new_node != current_node:
                        current_node = new_node

                new_dump = ast.dump(current_node)
                if new_dump == last_dump:
                    break
                last_dump = new_dump
                LOGGER.info(
                    f"Completed iteration {cur}/?, size of node: {len(new_dump)}"
                )
                cur += 1

                if cur > self.max_iterations:
                    LOGGER.warning(
                        f"Reached maximum iterations ({self.max_iterations}). Stopping."
                    )
                    break
        else:
            for _ in range(self.iterations):
                for transformer in self.transformers:
                    new_node = self.run_transformer(transformer, current_node)

                    if new_node != current_node:
                        current_node = new_node

                LOGGER.info(
                    f"Completed iteration {_ + 1}/{self.iterations}, size of node: {len(ast.dump(current_node))}"
                )

        return current_node
