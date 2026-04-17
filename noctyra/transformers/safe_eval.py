from noctyra.core import Variable, supported_types, supported_iterator
from noctyra.utils import ATTR, BIN_OPS, UNARY_OPS, COMP_OPS, FUNCS, WHITELIST, LOGGER
from noctyra.core import Context, LambdaType, SymbolicValue, NoneValue, ImportSymbol
from typing import Any
import operator
import ast


class SafeEval(ast.NodeVisitor):
    def __init__(
        self,
        ctx: Context | None = None,
        depth: int = 0,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ) -> None:
        self.depth = depth
        self.max_depth = max_depth
        self.max_allocation = max_allocation
        self.ctx = ctx or Context()

    def exec_custom_func(
        self,
        fn: LambdaType,
        args: list[supported_types] | None = None,
        kwargs: dict[str, supported_types] | None = None,
    ):

        if args is None:
            args = []

        if kwargs is None:
            kwargs = {}

        new_args = [
            Variable(fn.get_args().args[i].arg, arg) for i, arg in enumerate(args)
        ]
        new_kwargs = [Variable(name, val) for name, val in kwargs.items()]

        return SafeEval(
            Context(new_args + new_kwargs, self.ctx),
            depth=self.depth + 1,
            max_depth=self.max_depth,
            max_allocation=self.max_allocation,
        ).visit(fn.get_body())

    def unwrap(self, obj):
        """Méthode helper à ajouter dans ta classe SafeEval"""
        if hasattr(obj, "value"):  # Vérifie si c'est un SymbolicValue
            return self.unwrap(obj.value)
        if isinstance(obj, list):
            return [self.unwrap(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self.unwrap(x) for x in obj)
        if isinstance(obj, set):
            return {self.unwrap(x) for x in obj}
        if isinstance(obj, dict):
            return {self.unwrap(k): self.unwrap(v) for k, v in obj.items()}
        return obj

    def get_name_obf(self, node: ast.AST):
        if isinstance(node, ast.Name):
            return node.id

        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                return self.visit(node.args[0])

    def check_size(self, obj):
        val = self.unwrap(obj)
        if isinstance(val, (str, bytes, list, dict, set, tuple)):
            if len(val) > self.max_allocation:
                LOGGER.debug(f"Size limit exceeded for {type(val).__name__}")
                return True
        elif isinstance(val, (int, float)):
            if val > self.max_allocation or val < -self.max_allocation:
                LOGGER.debug(f"Numeric limit exceeded for {type(val).__name__}")
                return True

        return False

    def visit(self, node: ast.AST | None):

        if self.depth >= self.max_depth:
            LOGGER.debug("Max recursion depth reached")
            return None

        if node is None:
            return None

        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)

        if visitor == self.generic_visit:
            return None

        return visitor(node)

    def visit_Lambda(self, node: ast.Lambda) -> Any:

        func = LambdaType(node.body, node.args)

        return lambda *args, **kwargs: self.exec_custom_func(func, args, kwargs)  # type: ignore

    def visit_BinOp(self, node):
        left_res = self.visit(node.left)
        right_res = self.visit(node.right)

        if left_res is None or right_res is None:
            return None

        left = self.unwrap(left_res)
        right = self.unwrap(right_res)

        op = BIN_OPS.get(type(node.op))

        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            return None

        if isinstance(right, int) and op in (operator.mul, operator.pow):
            try:
                if self.check_size(right):  # type: ignore
                    return None

            except Exception:
                return None

        if isinstance(left, (str, list)) and isinstance(right, int):
            if self.check_size(right):
                return None

        if op is None:
            LOGGER.warning(f"Unsupported op: {type(node.op)}")
            return None

        try:
            res = op(left, right)

            if self.check_size(res):
                return None
            LOGGER.debug(
                f"BinOp: {left!r} {type(node.op).__name__} {right!r} -> {res!r}"
            )
            return res
        except Exception as e:
            LOGGER.debug(f"BinOp failed: {e}")
            return None

    def visit_Subscript(self, node: ast.Subscript):

        value_res = self.visit(node.value)

        if value_res is None:
            return None

        value = self.unwrap(value_res)
        _slice_res = self.visit(node.slice)

        if _slice_res is None:
            return None

        _slice = self.unwrap(_slice_res)

        try:
            res = value[_slice]  # type: ignore
            if self.check_size(res):
                return None
            return res
        except Exception:
            LOGGER.debug(f"Subscript failed. {value=}, {_slice=}")
            return None

    def visit_BoolOp(self, node: ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = None
            for value in node.values:
                res = self.visit(value)
                if res is None:
                    return None
                result = self.unwrap(res)
                if not result:
                    return result
            return result

        else:
            result = None
            for value in node.values:
                res = self.visit(value)
                if res is None:
                    return None
                result = self.unwrap(res)
                if result:
                    return result
            return result

    def visit_Slice(self, node: ast.Slice):

        lower = self.visit(node.lower)
        upper = self.visit(node.upper)
        step = self.visit(node.step)

        if all(i is None for i in [lower, upper, step]):
            return

        return slice(self.unwrap(lower), self.unwrap(upper), self.unwrap(step))

    def visit_UnaryOp(self, node: ast.UnaryOp):

        op = UNARY_OPS.get(type(node.op))

        if op is None:
            return None

        operand = self.visit(node.operand)

        if operand is None:
            return None

        try:
            res = op(self.unwrap(operand))
            if self.check_size(res):
                return None
            return res
        except Exception:
            return None

    def visit_Call(self, node: ast.Call):

        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            if func_name in FUNCS:
                func = FUNCS[func_name]

                args_res = [self.visit(arg) for arg in node.args]
                kwargs_res = {
                    kwarg.arg: self.visit(kwarg.value)
                    for kwarg in node.keywords
                    if kwarg.arg
                }
                if any(arg is None for arg in args_res):
                    return None

                if any(v is None for v in kwargs_res.values()):
                    return None

                if func is map:
                    fn = args_res[0]
                    arg = self.unwrap(args_res[1])
                    if isinstance(fn, LambdaType) and isinstance(
                        arg, supported_iterator
                    ):
                        if self.check_size(arg):
                            return None

                        return [self.exec_custom_func(fn, [x]) for x in arg]  # type: ignore

                elif func is zip:
                    if all(i is not None for i in args_res):
                        args = [self.unwrap(a) for a in args_res]
                        for a in args:
                            if isinstance(a, supported_iterator) and self.check_size(a):
                                return None
                        return list(zip(*args))

                else:

                    try:
                        args = [self.unwrap(a) for a in args_res]
                        kwargs = {k: self.unwrap(v) for k, v in kwargs_res.items()}
                        res = func(*args, **kwargs)

                        if self.check_size(res):
                            return None
                        LOGGER.debug(f"Call {func_name}({args}) -> {res!r}")
                        return res
                    except Exception as e:
                        LOGGER.debug(f"Call {func_name} failed: {e}")
                        return None
            elif self.ctx.has(func_name):

                func_entry = self.ctx.get(func_name)

                if func_entry is None:
                    return None

                func = func_entry.get()

                if not isinstance(func, LambdaType):
                    return None

                args_res = [self.visit(arg) for arg in node.args]
                kwargs_res = {
                    kwarg.arg: self.visit(kwarg.value)
                    for kwarg in node.keywords
                    if kwarg.arg
                }

                if any(arg is None for arg in args_res):
                    return None

                if any(v is None for v in kwargs_res.values()):
                    return None

                args = [self.unwrap(a) for a in args_res]
                kwargs = {k: self.unwrap(v) for k, v in kwargs_res.items()}

                res = self.exec_custom_func(func, args, kwargs)  # type: ignore
                if self.check_size(res):
                    return None
                return res

            elif isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str
            ):

                if func_name == "eval":
                    nd = ast.parse(node.args[0].value).body[0]

                    if isinstance(nd, ast.Expr):
                        return self.visit(nd.value)

                elif func_name == "__import__":
                    return ImportSymbol(node.args[0].value)

        elif isinstance(node.func, ast.Attribute):

            result = self.visit(node.func)

            if result is not None:
                if self.check_size(result):
                    return None

                return result

            attr_name = node.func.attr

            if attr_name in ATTR:
                val_res = self.visit(node.func.value)
                if val_res is not None:
                    value = self.unwrap(val_res)
                    try:
                        args_res = [self.visit(arg) for arg in node.args]
                        if any(arg is None for arg in args_res):
                            return None

                        args = [self.unwrap(a) for a in args_res]

                        func = getattr(value, attr_name)
                        result = func(*args)

                        if not isinstance(result, supported_types):
                            return None

                        if self.check_size(result):
                            return None

                        LOGGER.debug(
                            f"Attr call: {type(value).__name__}.{attr_name} -> {result!r}"
                        )
                        return result

                    except Exception:
                        return None

            module = self.visit(node.func.value)

            if isinstance(module, ImportSymbol) and module.module in WHITELIST and attr_name in WHITELIST[module.module]:
                func = WHITELIST[module.module][attr_name]
                args_res = [self.visit(arg) for arg in node.args]

                if any(arg is None for arg in args_res):
                    return None

                args = [self.unwrap(a) for a in args_res]

                try:
                    result = func(*args)
                    if not isinstance(result, supported_types):
                        return None

                    if self.check_size(result):
                        return None

                    LOGGER.debug(
                        f"Resolved encoding call: {module.module}.{attr_name} -> {result!r}"
                    )
                    return result  # type: ignore
                except Exception as e:
                    LOGGER.debug(f"Failed to resolve encoding call: {e}")

            return None

        return None

    def visit_Constant(self, node: ast.Constant):
        if node.value is None:
            return NoneValue()
        return SymbolicValue(node.value, node)

    def visit_Name(self, node: ast.Name):
        if (entry := self.ctx.get(node.id)) is not None:
            result = entry.get()
            return result

        return None

    def visit_List(self, node: ast.List):
        res = [self.visit(elt) for elt in node.elts]
        if any(v is None for v in res):
            return None
        if self.check_size(res):
            return None
        return res

    def visit_Set(self, node: ast.Set):
        res = set([self.visit(elt) for elt in node.elts])
        if any(v is None for v in res):
            return None
        if self.check_size(res):
            return None
        return res

    def visit_Tuple(self, node: ast.Tuple):
        res = tuple([self.visit(elt) for elt in node.elts])
        if any(v is None for v in res):
            return None
        if self.check_size(res):
            return None
        return res

    def visit_IfExp(self, node: ast.IfExp):

        cond_res = self.visit(node.test)

        if cond_res is None:
            return None

        cond = self.unwrap(cond_res)

        result = self.visit(node.body) if cond else self.visit(node.orelse)

        return result

    def visit_Compare(self, node: ast.Compare):

        if len(node.ops) != len(node.comparators):
            return None

        try:
            left_res = self.visit(node.left)
            if left_res is None:
                return None

            left = self.unwrap(left_res)

            for i, op in enumerate(node.ops):
                right_res = self.visit(node.comparators[i])
                if right_res is None:
                    return None

                right = self.unwrap(right_res)

                fn = COMP_OPS.get(type(op))
                if fn is None:
                    return None

                if not fn(left, right):
                    return False
                left = right

            return True
        except Exception as e:
            LOGGER.debug(f"Compare failed: {e}")
            return None


def safe_eval(
    node: ast.AST | None,
    ctx: Context | None = None,
    max_depth: int = 50,
    max_allocation: int = 100_000,
) -> None | Any:

    return SafeEval(ctx, max_depth=max_depth, max_allocation=max_allocation).visit(node)
