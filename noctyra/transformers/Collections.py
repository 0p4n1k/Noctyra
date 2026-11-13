import ast
from typing import Any

from noctyra.core import is_symbolic_ref
from noctyra.core.Transformer import UNRESOLVED, BaseTransformer
from noctyra.utils import IMMUTABLE_TYPES, LOGGER


class CollectionsTransformer(BaseTransformer):
    """Fold constant collection subscripts and builtin sequence/aggregate calls."""

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.ctx, ast.Load):
            return node

        val: Any = UNRESOLVED
        res = self.eval(node)
        if res is not None and not is_symbolic_ref(res):
            val = self.unwrap(res)
        else:
            target = self._eval_const_expr(node.value, eval_subscripts=True)
            key = self._eval_const_expr(node.slice, eval_subscripts=True)
            if target is not UNRESOLVED and key is not UNRESOLVED:
                if isinstance(
                    target, (list, tuple, dict, str, bytes)
                ) and self._within_allocation(target):
                    try:
                        val = target[key]
                    except Exception:
                        val = UNRESOLVED

        if (
            val is not UNRESOLVED
            and not is_symbolic_ref(val)
            and isinstance(val, IMMUTABLE_TYPES)
            and self._within_allocation(val)
        ):
            LOGGER.debug(f"Folded Subscript into constant: {val!r}")
            return ast.copy_location(ast.Constant(value=val), node)

        return node

    def _is_reversed_call(self, node: ast.AST) -> ast.Call | None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "reversed"
            and self._is_builtin_usable("reversed")
            and not node.keywords
            and len(node.args) == 1
        ):
            return node
        return None

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if node.keywords:
            return node

        # Handle "".join(reversed(s))
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and len(node.args) == 1
        ):
            rev_call = self._is_reversed_call(node.args[0])
            if rev_call is None:
                return node
            sep = self._eval_const_expr(node.func.value, eval_subscripts=True)
            seq = self._eval_const_expr(rev_call.args[0], eval_subscripts=True)
            if not isinstance(sep, str) or seq is UNRESOLVED:
                return node
            if isinstance(seq, str) and len(seq) <= self.max_allocation:
                est = len(seq) + len(sep) * max(0, len(seq) - 1)
                if est > self.max_allocation:
                    return node
                joined = sep.join(reversed(seq))
                if len(joined) <= self.max_allocation:
                    LOGGER.debug(
                        f"Folded join(reversed(...)) into constant: {joined!r}"
                    )
                    return ast.copy_location(ast.Constant(value=joined), node)
            elif (
                isinstance(seq, (list, tuple))
                and len(seq) <= self.max_allocation
                and all(isinstance(el, str) for el in seq)
            ):
                est = sum(len(el) for el in seq) + len(sep) * max(0, len(seq) - 1)
                if est > self.max_allocation:
                    return node
                joined = sep.join(reversed(seq))
                if len(joined) <= self.max_allocation:
                    LOGGER.debug(
                        f"Folded join(reversed(...)) into constant: {joined!r}"
                    )
                    return ast.copy_location(ast.Constant(value=joined), node)
            return node

        if not isinstance(node.func, ast.Name):
            return node

        func_name = node.func.id
        if not self._is_builtin_usable(func_name):
            return node

        if func_name == "len" and len(node.args) == 1:
            val = self._eval_const_expr(node.args[0], eval_subscripts=True)
            if (
                isinstance(val, (str, bytes, list, tuple, dict, set))
                and len(val) <= self.max_allocation
            ):
                length = len(val)
                LOGGER.debug(f"Folded len(...) into constant: {length!r}")
                return ast.copy_location(ast.Constant(value=length), node)
            return node

        if func_name == "sum" and len(node.args) == 1:
            val = self._eval_const_expr(node.args[0], eval_subscripts=True)
            if (
                isinstance(val, (list, tuple, set))
                and len(val) <= self.max_allocation
                and all(isinstance(el, (int, float)) for el in val)
            ):
                total = sum(val)
                if isinstance(total, IMMUTABLE_TYPES):
                    LOGGER.debug(f"Folded sum(...) into constant: {total!r}")
                    return ast.copy_location(ast.Constant(value=total), node)
            return node

        if func_name in ("min", "max") and len(node.args) >= 1:
            items: list[Any]
            if len(node.args) == 1:
                val = self._eval_const_expr(node.args[0], eval_subscripts=True)
                if (
                    not isinstance(val, (list, tuple, set, str))
                    or not val
                    or len(val) > self.max_allocation
                ):
                    return node
                items = list(val)
            else:
                items = []
                for arg in node.args:
                    arg_val = self._eval_const_expr(arg, eval_subscripts=True)
                    if arg_val is UNRESOLVED:
                        return node
                    items.append(arg_val)

            if not all(isinstance(el, (int, float, str)) for el in items):
                return node

            try:
                result = min(items) if func_name == "min" else max(items)
            except (TypeError, ValueError):
                return node

            if isinstance(result, IMMUTABLE_TYPES):
                LOGGER.debug(f"Folded {func_name}(...) into constant: {result!r}")
                return ast.copy_location(ast.Constant(value=result), node)
            return node

        if func_name == "list" and len(node.args) == 1:
            rev_call = self._is_reversed_call(node.args[0])
            if rev_call is None:
                return node
            seq = self._eval_const_expr(rev_call.args[0], eval_subscripts=True)
            if (
                isinstance(seq, (list, tuple, str, bytes))
                and len(seq) <= self.max_allocation
            ):
                rev_items = list(reversed(seq))
                if all(isinstance(el, IMMUTABLE_TYPES) for el in rev_items):
                    elts: list[ast.expr] = [
                        ast.copy_location(ast.Constant(value=el), node)
                        for el in rev_items
                    ]
                    LOGGER.debug(
                        f"Folded list(reversed(...)) into list of {len(elts)} constants"
                    )
                    return ast.copy_location(ast.List(elts=elts, ctx=ast.Load()), node)
            return node

        return node
