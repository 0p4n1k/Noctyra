import ast
from typing import Any

from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import IMMUTABLE_TYPES, LOGGER

_UNRESOLVED = object()


class BuiltinFolder(BaseTransformer):
    """Fold pure builtin calls into AST constants, lists, or dicts."""

    def _within_allocation(self, value: Any) -> bool:
        if isinstance(value, (str, bytes, list, tuple, dict, set)):
            return len(value) <= self.max_allocation
        return True

    def _eval_expr(self, node: ast.AST | None) -> Any:
        if node is None:
            return _UNRESOLVED

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

        return _UNRESOLVED

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if node.keywords or not isinstance(node.func, ast.Name):
            return node

        func_name = node.func.id

        if func_name == "int" and len(node.args) == 2:
            s = self._eval_expr(node.args[0])
            base = self._eval_expr(node.args[1])
            if (
                isinstance(s, (str, bytes))
                and isinstance(base, int)
                and not isinstance(base, bool)
            ):
                try:
                    int_res = int(s, base)
                except (ValueError, TypeError, OverflowError):
                    return node
                if abs(int_res) <= self.max_allocation:
                    LOGGER.debug(
                        f"Folded int({s!r}, {base!r}) into constant: {int_res!r}"
                    )
                    return ast.copy_location(ast.Constant(value=int_res), node)
            return node

        if func_name in ("bin", "oct", "ascii", "repr") and len(node.args) == 1:
            val = self._eval_expr(node.args[0])
            if val is _UNRESOLVED or not isinstance(val, IMMUTABLE_TYPES):
                return node
            try:
                if func_name in ("bin", "oct"):
                    if not isinstance(val, int):
                        return node
                    if val.bit_length() > self.max_allocation:
                        return node
                    str_res = bin(val) if func_name == "bin" else oct(val)
                elif func_name == "ascii":
                    str_res = ascii(val)
                else:
                    str_res = repr(val)
            except (TypeError, ValueError, OverflowError):
                return node
            if len(str_res) <= self.max_allocation:
                LOGGER.debug(f"Folded {func_name}(...) into constant: {str_res!r}")
                return ast.copy_location(ast.Constant(value=str_res), node)
            return node

        if func_name in ("any", "all") and len(node.args) == 1:
            it = self._eval_expr(node.args[0])
            if (
                isinstance(it, (list, tuple, set, str, bytes, dict))
                and len(it) <= self.max_allocation
            ):
                bool_res = bool(any(it) if func_name == "any" else all(it))
                LOGGER.debug(f"Folded {func_name}(...) into constant: {bool_res!r}")
                return ast.copy_location(ast.Constant(value=bool_res), node)
            return node

        if func_name == "sorted" and len(node.args) == 1:
            it = self._eval_expr(node.args[0])
            if (
                isinstance(it, (list, tuple, set, str, bytes, dict))
                and len(it) <= self.max_allocation
                and all(isinstance(el, IMMUTABLE_TYPES) for el in it)
            ):
                try:
                    sorted_items = sorted(it)
                except TypeError:
                    return node
                elts: list[ast.expr] = [
                    ast.copy_location(ast.Constant(value=v), node) for v in sorted_items
                ]
                LOGGER.debug(f"Folded sorted(...) into list of {len(elts)} constants")
                return ast.copy_location(ast.List(elts=elts, ctx=ast.Load()), node)
            return node

        if func_name == "dict" and len(node.args) == 1:
            arg = node.args[0]
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "zip"
                and not arg.keywords
                and len(arg.args) == 2
            ):
                keys_seq = self._eval_expr(arg.args[0])
                vals_seq = self._eval_expr(arg.args[1])
                if (
                    isinstance(keys_seq, (list, tuple, str, bytes))
                    and isinstance(vals_seq, (list, tuple, str, bytes))
                    and len(keys_seq) <= self.max_allocation
                    and len(vals_seq) <= self.max_allocation
                    and all(isinstance(k, IMMUTABLE_TYPES) for k in keys_seq)
                    and all(isinstance(v, IMMUTABLE_TYPES) for v in vals_seq)
                ):
                    try:
                        folded_dict = dict(zip(keys_seq, vals_seq))
                    except TypeError:
                        return node
                    keys: list[ast.expr | None] = [
                        ast.copy_location(ast.Constant(value=k), node)
                        for k in folded_dict.keys()
                    ]
                    values: list[ast.expr] = [
                        ast.copy_location(ast.Constant(value=v), node)
                        for v in folded_dict.values()
                    ]
                    LOGGER.debug(
                        f"Folded dict(zip(...)) into dict of {len(keys)} entries"
                    )
                    return ast.copy_location(ast.Dict(keys=keys, values=values), node)
            pairs_seq = self._eval_expr(arg)
            if (
                isinstance(pairs_seq, (list, tuple))
                and len(pairs_seq) <= self.max_allocation
                and all(
                    isinstance(p, (list, tuple))
                    and len(p) == 2
                    and isinstance(p[0], IMMUTABLE_TYPES)
                    and isinstance(p[1], IMMUTABLE_TYPES)
                    for p in pairs_seq
                )
            ):
                try:
                    folded_dict = dict(pairs_seq)
                except TypeError:
                    return node
                keys = [
                    ast.copy_location(ast.Constant(value=k), node)
                    for k in folded_dict.keys()
                ]
                values = [
                    ast.copy_location(ast.Constant(value=v), node)
                    for v in folded_dict.values()
                ]
                LOGGER.debug(f"Folded dict(...) into dict of {len(keys)} entries")
                return ast.copy_location(ast.Dict(keys=keys, values=values), node)
            return node

        return node
