import ast

from noctyra.core.Transformer import UNRESOLVED, BaseTransformer
from noctyra.utils import IMMUTABLE_TYPES, LOGGER


class BuiltinFolder(BaseTransformer):
    """Fold pure builtin calls into AST constants, lists, or dicts."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if node.keywords or not isinstance(node.func, ast.Name):
            return node

        func_name = node.func.id
        if not self._is_builtin_usable(func_name):
            return node

        if func_name == "int" and len(node.args) == 2:
            s = self._eval_const_expr(node.args[0])
            base = self._eval_const_expr(node.args[1])
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
            val = self._eval_const_expr(node.args[0])
            if val is UNRESOLVED or not isinstance(val, IMMUTABLE_TYPES):
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
            it = self._eval_const_expr(node.args[0])
            if (
                isinstance(it, (list, tuple, set, str, bytes, dict))
                and len(it) <= self.max_allocation
            ):
                bool_res = bool(any(it) if func_name == "any" else all(it))
                LOGGER.debug(f"Folded {func_name}(...) into constant: {bool_res!r}")
                return ast.copy_location(ast.Constant(value=bool_res), node)
            return node

        if func_name == "sorted" and len(node.args) == 1:
            it = self._eval_const_expr(node.args[0])
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
                and self._is_builtin_usable("zip")
                and not arg.keywords
                and len(arg.args) == 2
            ):
                keys_seq = self._eval_const_expr(arg.args[0])
                vals_seq = self._eval_const_expr(arg.args[1])
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
            pairs_seq = self._eval_const_expr(arg)
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
