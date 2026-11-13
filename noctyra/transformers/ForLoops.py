from noctyra.core import Context, Variable, is_symbolic_ref, to_node
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
from typing import Any, List
import ast

_EAGER_GENERATOR_BUILTINS = frozenset(
    {"bytes", "bytearray", "list", "tuple", "set", "sum", "any", "all", "sorted", "min", "max"}
)


class LCTransformer(BaseTransformer):

    def _get_vars_from_target(
        self, target: ast.AST, item: Any
    ) -> List[Variable] | None:

        if isinstance(target, ast.Name):
            return [Variable(name=target.id, value=item)]
        if isinstance(target, (ast.Tuple, ast.List)):
            if any(isinstance(e, ast.Starred) for e in target.elts):
                return None
            if not isinstance(item, (list, tuple, str, bytes, range, set, dict)):
                return None
            seq = list(item)
            if len(target.elts) != len(seq):
                return None
            vars_list: list[Variable] = []
            for t, v in zip(target.elts, seq):
                sub = self._get_vars_from_target(t, v)
                if sub is None:
                    return None
                vars_list.extend(sub)
            return vars_list
        return None

    def _evaluate_comprehension_like(
        self, node_elt: ast.AST, generators: List[ast.comprehension]
    ) -> List[Any] | None:
        steps = 0

        def recurse(gen_idx: int, current_ctx: Context) -> List[Any] | None:
            nonlocal steps
            if gen_idx == len(generators):
                val = self.eval(node_elt, current_ctx)
                if val is None or is_symbolic_ref(val):
                    return None
                return [val]

            gen = generators[gen_idx]
            iterable_res = self.eval(gen.iter, current_ctx)
            if iterable_res is None or is_symbolic_ref(iterable_res):
                return None

            iterable = self.unwrap(iterable_res)
            if not isinstance(iterable, (list, tuple, str, bytes, range, set, dict)):
                return None
            try:
                if len(iterable) > self.max_allocation:
                    return None
            except OverflowError:
                return None

            res: list[Any] = []
            for item in iterable:
                steps += 1
                if steps > self.max_allocation:
                    return None
                _vars = self._get_vars_from_target(gen.target, item)
                if _vars is None:
                    return None
                new_ctx = Context(_vars, current_ctx)
                cond_ok = True
                for if_cond in gen.ifs:
                    c_res = self.eval(if_cond, new_ctx)
                    if c_res is None or is_symbolic_ref(c_res):
                        return None
                    if not self.unwrap(c_res):
                        cond_ok = False
                        break
                if cond_ok:
                    sub_res = recurse(gen_idx + 1, new_ctx)
                    if sub_res is None:
                        return None
                    res.extend(sub_res)
                    if len(res) > self.max_allocation:
                        return None
            return res

        return recurse(0, self.ctx)

    def visit_ListComp(self, node: ast.ListComp):
        self.generic_visit(node)
        try:
            res = self._evaluate_comprehension_like(node.elt, node.generators)
            if res is not None:
                folded = to_node(self.unwrap(res))
                if folded is not None:
                    LOGGER.debug(f"Folded list comprehension: {len(res)} items")
                    return ast.copy_location(folded, node)
        except Exception as e:
            LOGGER.debug(f"List comprehension folding failed: {e}")
        return node

    def visit_Call(self, node: ast.Call):
        super().visit_Call(node)
        if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.GeneratorExp):
            return node

        gen = node.args[0]
        is_eager = False
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in _EAGER_GENERATOR_BUILTINS
            and self._is_builtin_usable(node.func.id)
        ):
            is_eager = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            recv_res = self.eval(node.func.value)
            if (
                recv_res is not None
                and not is_symbolic_ref(recv_res)
                and isinstance(self.unwrap(recv_res), (str, bytes))
            ):
                is_eager = True

        if not is_eager:
            return node

        try:
            res = self._evaluate_comprehension_like(gen.elt, gen.generators)
            if res is not None:
                list_node = to_node(self.unwrap(res))
                if list_node is not None:
                    node.args[0] = ast.copy_location(list_node, gen)
        except Exception as e:
            LOGGER.debug(f"Eager generator folding failed: {e}")
        return node
