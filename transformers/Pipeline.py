from utils.logger import LOGGER
from typing import List, Type
from classes import Context
import ast


class TransformerPipeline(ast.NodeTransformer):
    def __init__(
        self,
        transformers: List[Type[ast.NodeTransformer]],
        iterations: int = 0,
        max_iterations: int = 100,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ):
        self.transformers = [t() for t in transformers]
        self.iterations = iterations
        self.max_iterations = max_iterations
        self.max_allocation = max_allocation
        self.max_depth = max_depth
        LOGGER.info(
            f"Initialized TransformerPipeline with {len(self.transformers)} transformers and {self.iterations if self.iterations > 0 else 'auto'} iterations."
        )

    def run_transformer(
        self, transformer: ast.NodeTransformer, node: ast.AST, ctx: Context
    ) -> ast.AST:

        return getattr(
            transformer,
            "run",
            (lambda node, ctx, max_depth, max_allocation: transformer.visit(node)),
        )(node, ctx, self.max_depth, self.max_allocation)

    def visit(self, node):

        current_node = node

        if self.iterations == 0:
            last_size = len(ast.dump(current_node))
            cur = 1
            while True:
                for transformer in self.transformers:
                    ctx = Context.from_tree(current_node)

                    new_node = self.run_transformer(transformer, current_node, ctx)

                    if new_node != current_node:
                        current_node = new_node

                new_size = len(ast.dump(current_node))
                if new_size == last_size:
                    break
                last_size = new_size
                LOGGER.info(f"Completed iteration {cur}/?, size of node: {new_size}")
                cur += 1

                if cur > self.max_iterations:
                    LOGGER.warning(
                        f"Reached maximum iterations ({self.max_iterations}). Stopping."
                    )
                    break
        else:
            for _ in range(self.iterations):
                for transformer in self.transformers:
                    ctx = Context.from_tree(current_node)
                    new_node = self.run_transformer(transformer, current_node, ctx)

                    if new_node != current_node:
                        current_node = new_node

                LOGGER.info(
                    f"Completed iteration {_ + 1}/{self.iterations}, size of node: {len(ast.dump(current_node))}"
                )

        return current_node
