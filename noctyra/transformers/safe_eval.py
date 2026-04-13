from noctyra.core import Variable, supported_types, supported_iterator
from noctyra.utils import ATTR, OPS, FUNCS, ENCODING, LOGGER
from noctyra.core import Context, CustomFunction
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
        fn: CustomFunction,
        args: list[supported_types] | None = None,
        kwargs: dict[str, supported_types] | None = None,
    ):

        if args is None:
            args = []

        if kwargs is None:
            kwargs = {}

        new_args = [Variable(fn.args.args[i].arg, arg) for i, arg in enumerate(args)]
        new_kwargs = [Variable(name, val) for name, val in kwargs.items()]

        return SafeEval(
            self.ctx.copy_with(new_args + new_kwargs),
            depth=self.depth + 1,
        ).visit(fn.body)

    def get_name_obf(self, node: ast.AST):
        if isinstance(node, ast.Name):
            return node.id

        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                return self.visit(node.args[0])

    def check_size(self, obj):
        if isinstance(obj, (str, bytes, list, dict, set)):
            if len(obj) > self.max_allocation:
                LOGGER.debug(f"Size limit exceeded for {type(obj).__name__}")
                return True
        elif isinstance(obj, (int, float)):
            if obj > self.max_allocation or obj < -self.max_allocation:
                LOGGER.debug(f"Numeric limit exceeded for {type(obj).__name__}")
                return True

        return False

    def visit(self, node: ast.AST | None):

        if self.depth >= self.max_depth or node is None:
            LOGGER.debug("Max recursion depth reached")
            return None

        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)

        if visitor == self.generic_visit:
            return None

        return visitor(node)

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)

        if right is None or left is None:
            return None

        op = OPS.get(type(node.op))

        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            return None

        if isinstance(right, int) and op in (operator.mul, operator.pow):
            try:
                if self.check_size(right):  # type: ignore
                    return None

            except Exception:
                return None

        if isinstance(left, (str, list)) and isinstance(right, int):
            return None

        if op is None:
            LOGGER.debug(f"Unsupported op: {type(node.op)}")
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
        self.generic_visit(node)
        value = self.visit(node.value)

        if value is None:
            return None

        _slice = self.visit(node.slice)

        if _slice is None:
            return None

        if isinstance(_slice, str):
            if not hasattr(value, _slice):
                return None

        elif isinstance(_slice, int):
            if len(value) < _slice:
                return None

        try:
            return value[_slice]
        except Exception:
            LOGGER.warning(f"Error on visit_Subscript. {value=}, {_slice=}")
            return None

    def visit_BoolOp(self, node: ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = None
            for value in node.values:
                result = self.visit(value)
                if not result:
                    return result
            return result

        else:
            result = None
            for value in node.values:
                result = self.visit(value)
                if result:
                    return result
            return result

    def visit_Slice(self, node: ast.Slice):

        lower = self.visit(node.lower)
        upper = self.visit(node.upper)
        step = self.visit(node.step)

        return slice(lower, upper, step)

    def visit_UnaryOp(self, node: ast.UnaryOp):

        op = OPS.get(type(node.op))

        if op is None:
            return None

        operand = self.visit(node.operand)

        if operand is None:
            return None

        return op(operand)

    def visit_Call(self, node: ast.Call):

        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            if func_name in FUNCS:
                func = FUNCS[func_name]

                args = [self.visit(arg) for arg in node.args]
                kwargs = {
                    kwarg.arg: self.visit(kwarg.value)
                    for kwarg in node.keywords
                    if kwarg.arg
                }
                if any(arg is None for arg in args):
                    return None

                if any(kwargs is None for kwargs in kwargs.values()):
                    return None

                if func is map:
                    fn = args[0]
                    arg = args[1]
                    if isinstance(fn, CustomFunction) and isinstance(
                        arg, supported_iterator
                    ):
                        return [self.exec_custom_func(fn, [x]) for x in arg]

                elif func is zip:
                    if all(i is not None for i in args):
                        return list(zip(*args))

                else:

                    try:
                        res = func(*args, **kwargs)
                        LOGGER.debug(f"Call {func_name}({args}) -> {res!r}")
                        return res
                    except Exception as e:
                        LOGGER.debug(f"Call {func_name} failed: {e}")
                        return None

            elif self.ctx.has(func_name):

                func = self.ctx.get(func_name)

                if func is None:
                    return None

                func = func.get()

                if not isinstance(func, CustomFunction):
                    return None

                args = [self.visit(arg) for arg in node.args]
                kwargs = {
                    kwarg.arg: self.visit(kwarg.value)
                    for kwarg in node.keywords
                    if kwarg.arg
                }

                if not all(isinstance(v, supported_types) for v in args):
                    return None

                if not all(isinstance(v, supported_types) for v in kwargs.values()):
                    return None

                return self.exec_custom_func(func, args, kwargs)  # type: ignore

        if isinstance(node.func, ast.Attribute):

            result = self.visit(node.func)

            if result is not None:
                return result

            attr_name = node.func.attr

            if attr_name in ATTR:
                value = self.visit(node.func.value)
                if value is not None:
                    try:
                        args = [self.visit(arg) for arg in node.args]
                        func = getattr(value, attr_name)
                        result = func(*args)

                        if not isinstance(result, supported_types):
                            return None

                        LOGGER.debug(
                            f"Attr call: {type(value).__name__}.{attr_name} -> {result!r}"
                        )
                        return result

                    except Exception:
                        return None

            module_name = self.get_name_obf(node.func.value)

            if module_name in ENCODING and attr_name in ENCODING[module_name]:
                func = ENCODING[module_name][attr_name]
                args = [self.visit(arg) for arg in node.args]

                if any(arg is None for arg in args):
                    return None

                try:
                    result = func(*args)
                    if not isinstance(result, supported_types):
                        return None
                    LOGGER.debug(
                        f"Resolved encoding call: {module_name}.{attr_name} -> {result!r}"
                    )
                    return result  # type: ignore
                except Exception as e:
                    LOGGER.debug(f"Failed to resolve encoding call: {e}")

            return None

        return None

    def visit_Constant(self, node: ast.Constant):
        return node.value

    def visit_Name(self, node: ast.Name):
        if (entry := self.ctx.get(node.id)) is not None:
            result = entry.get()
            return result

        return None

    def visit_List(self, node: ast.List):
        res = [self.visit(elt) for elt in node.elts]
        if any(v is None for v in res):
            return None
        return res

    def visit_Set(self, node: ast.Set):
        res = set([self.visit(elt) for elt in node.elts])
        if any(v is None for v in res):
            return None
        return res

    def visit_Tuple(self, node: ast.Tuple):
        res = tuple([self.visit(elt) for elt in node.elts])
        if any(v is None for v in res):
            return None
        return res

    def visit_IfExp(self, node: ast.IfExp):

        cond = self.visit(node.test)

        if cond is None:
            return None

        result = self.visit(node.body) if cond else self.visit(node.orelse)

        return result

    def visit_Compare(self, node: ast.Compare):

        if len(node.ops) != len(node.comparators):
            return None

        try:
            left = self.visit(node.left)
            if left is None:
                return None

            for i, op in enumerate(node.ops):
                right = self.visit(node.comparators[i])
                if right is None:
                    return None

                fn = OPS.get(type(op))
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
    node: ast.AST,
    ctx: Context | None = None,
    max_depth: int = 50,
    max_allocation: int = 100_000,
) -> None | Any:

    return SafeEval(ctx, max_depth=max_depth, max_allocation=max_allocation).visit(node)
