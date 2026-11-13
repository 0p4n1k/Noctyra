import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import IMMUTABLE_TYPES, LOGGER

_UNRESOLVED = object()


class CollectionsTransformer(BaseTransformer):
    """Fold constant collection subscripts and builtin sequence/aggregate calls."""

    def _within_allocation(self, value: Any) -> bool:
        if isinstance(value, (str, bytes, list, tuple, dict, set)):
            return len(value) <= self.max_allocation
        return True

    def _eval_expr(self, node: ast.AST | None) -> Any:
        if node is None:
            return None

        res = self.eval(node)
        if res is not None:
            val = self.unwrap(res)
            if self._within_allocation(val):
                return val
            return _UNRESOLVED

        if isinstance(node, ast.Dict):
            result: dict[Any, Any] = {}
            for k_node, v_node in zip(node.keys, node.values):
                if k_node is None:
                    spread = self._eval_expr(v_node)
                    if not isinstance(spread, dict):
                        return _UNRESOLVED
                    result.update(spread)
                else:
                    key = self._eval_expr(k_node)
                    val = self._eval_expr(v_node)
                    if key is _UNRESOLVED or val is _UNRESOLVED:
                        return _UNRESOLVED
                    try:
                        result[key] = val
                    except TypeError:
                        return _UNRESOLVED
                if len(result) > self.max_allocation:
                    return _UNRESOLVED
            return result

        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if len(node.elts) > self.max_allocation:
                return _UNRESOLVED
            items: list[Any] = []
            for elt in node.elts:
                if isinstance(elt, ast.Starred):
                    return _UNRESOLVED
                item = self._eval_expr(elt)
                if item is _UNRESOLVED:
                    return _UNRESOLVED
                items.append(item)
            if isinstance(node, ast.List):
                return items
            if isinstance(node, ast.Tuple):
                return tuple(items)
            try:
                return set(items)
            except TypeError:
                return _UNRESOLVED

        if isinstance(node, ast.Slice):
            lower = self._eval_expr(node.lower) if node.lower is not None else None
            upper = self._eval_expr(node.upper) if node.upper is not None else None
            step = self._eval_expr(node.step) if node.step is not None else None
            if lower is _UNRESOLVED or upper is _UNRESOLVED or step is _UNRESOLVED:
                return _UNRESOLVED
            return slice(lower, upper, step)

        if isinstance(node, ast.Subscript):
            target = self._eval_expr(node.value)
            key = self._eval_expr(node.slice)
            if target is _UNRESOLVED or key is _UNRESOLVED:
                return _UNRESOLVED
            try:
                val = target[key]
            except Exception:
                return _UNRESOLVED
            if self._within_allocation(val):
                return val
            return _UNRESOLVED

        return _UNRESOLVED

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.ctx, ast.Load):
            return node

        val = _UNRESOLVED
        res = self.eval(node)
        if res is not None:
            val = self.unwrap(res)
        else:
            target = self._eval_expr(node.value)
            key = self._eval_expr(node.slice)
            if target is not _UNRESOLVED and key is not _UNRESOLVED:
                if isinstance(
                    target, (list, tuple, dict, str, bytes)
                ) and self._within_allocation(target):
                    try:
                        val = target[key]
                    except Exception:
                        val = _UNRESOLVED

        if (
            val is not _UNRESOLVED
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
            sep = self._eval_expr(node.func.value)
            seq = self._eval_expr(rev_call.args[0])
            if not isinstance(sep, str) or seq is _UNRESOLVED:
                return node
            if isinstance(seq, str) and len(seq) <= self.max_allocation:
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

        if func_name == "len" and len(node.args) == 1:
            val = self._eval_expr(node.args[0])
            if (
                isinstance(val, (str, bytes, list, tuple, dict, set))
                and len(val) <= self.max_allocation
            ):
                length = len(val)
                LOGGER.debug(f"Folded len(...) into constant: {length!r}")
                return ast.copy_location(ast.Constant(value=length), node)
            return node

        if func_name == "sum" and len(node.args) == 1:
            val = self._eval_expr(node.args[0])
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
                val = self._eval_expr(node.args[0])
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
                    arg_val = self._eval_expr(arg)
                    if arg_val is _UNRESOLVED:
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
            seq = self._eval_expr(rev_call.args[0])
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
