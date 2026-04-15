from noctyra.core import Context, Variable
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
from typing import Any, Iterable, List
import ast


def to_node(v: Any) -> ast.expr | None:
    if isinstance(v, (int, float, str, bytes, bool, type(None), complex)):
        return ast.Constant(v)
    elif isinstance(v, list):
        content = [to_node(value) for value in v]
        if any(i is None for i in content):
            return None
        return ast.List(elts=content, ctx=ast.Load())  # type: ignore
    elif isinstance(v, tuple):
        content = [to_node(value) for value in v]
        if any(i is None for i in content):
            return None
        return ast.Tuple(elts=content, ctx=ast.Load())  # type: ignore
    elif isinstance(v, dict):
        keys = [to_node(k) for k in v.keys()]
        values = [to_node(val) for val in v.values()]
        if any(k is None for k in keys) or any(v is None for v in values):
            return None
        return ast.Dict(keys=keys, values=values)  # type: ignore
    elif isinstance(v, set):
        content = [to_node(value) for value in v]
        if any(i is None for i in content):
            return None
        return ast.Set(elts=content)  # type: ignore

    return None


class LCTransformer(BaseTransformer):

    def _get_vars_from_target(self, target: ast.AST, item: Any) -> List[Variable]:

        if isinstance(target, ast.Name):
            return [Variable(name=target.id, value=item)]
        elif isinstance(target, ast.Tuple) and isinstance(item, Iterable):
            vars_list = []
            for t, v in zip(target.elts, item):
                vars_list.extend(self._get_vars_from_target(t, v))
            return vars_list
        return []

    def _evaluate_comprehension_like(
        self, node_elt: ast.AST, generators: List[ast.comprehension]
    ) -> List[Any] | None:

        def recurse(gen_idx, current_ctx):
            if gen_idx == len(generators):
                val = self.eval(node_elt, current_ctx)
                return [val] if val is not None else [None]

            gen = generators[gen_idx]
            iterable = self.eval(gen.iter, current_ctx)

            if not isinstance(iterable, (list, tuple, str, bytes, range, set, dict)):
                return None

            res = []
            for item in iterable:
                _vars = self._get_vars_from_target(gen.target, item)
                new_ctx = Context(_vars, current_ctx)
                if all(self.eval(if_cond, new_ctx) for if_cond in gen.ifs):
                    sub_res = recurse(gen_idx + 1, new_ctx)
                    if sub_res is None:
                        return None
                    res.extend(sub_res)
            return res

        res = recurse(0, self.ctx)
        if res is not None and all(x is None for x in res):
            # If all evaluations failed but the loops finished, it's safer to not fold
            # unless it's explicitly [None, None]
            pass
        return res

    def visit_ListComp(self, node: ast.ListComp):
        self.generic_visit(node)
        try:
            res = self._evaluate_comprehension_like(node.elt, node.generators)
            if res is not None and not any(x is None for x in res):
                LOGGER.debug(f"Folded list comprehension: {len(res)} items")
                return to_node(res)
        except Exception as e:
            LOGGER.debug(f"List comprehension folding failed: {e}")
        return node

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        self.generic_visit(node)
        try:
            res = self._evaluate_comprehension_like(node.elt, node.generators)
            if res is not None and not any(x is None for x in res):
                LOGGER.debug(f"Folded generator expression: {len(res)} items")
                # For generator expressions, folding to a list is common in deobfuscation
                # but we return a list node here.
                return to_node(res)
        except Exception as e:
            LOGGER.debug(f"Generator folding failed: {e}")
        return node
