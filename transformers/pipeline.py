from utils.logger import LOGGER
from typing import List, Type
import ast



class TransformerPipeline(ast.NodeTransformer):
    def __init__(self, transformers: List[Type[ast.NodeTransformer]], iterations: int = 1, max_iterations: int = 10):
        self.transformers = [t() for t in transformers]
        self.iterations = iterations
        self.max_iterations = max_iterations
        LOGGER.info(f"Initialized TransformerPipeline with {len(self.transformers)} transformers and {self.iterations} iterations.")
        

    def visit(self, node):
        current_node = node
        for _ in range(self.iterations):
            for transformer in self.transformers:
                new_node = transformer.visit(current_node)
                if new_node != current_node:
                    current_node = new_node
        return current_node


