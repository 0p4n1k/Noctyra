from utils.shared import ATTR, OPS, FUNCS
from utils.logger import LOGGER
import operator
import ast

MAX_ALLOCATION = 100_000


class SafeEval(ast.NodeVisitor):
    def __init__(self, known_vars: dict | None = None) -> None:
        super().__init__()
        self.known_vars = known_vars or {}

    def get_name(self, name: str):
        return self.known_vars.get(name)

    def check_size(self, obj):
        if isinstance(obj, (str, bytes, list, dict, set)):
            if len(obj) > MAX_ALLOCATION:
                LOGGER.debug(f"Size limit exceeded for {type(obj).__name__}")
                return True
        elif isinstance(obj, (int, float)):
            if obj > MAX_ALLOCATION or obj < -MAX_ALLOCATION:
                LOGGER.debug(f"Numeric limit exceeded for {type(obj).__name__}")
                return True
        return False

    def visit(self, node):
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

        if (
            isinstance(left, (list, dict, set, str, bytes, int))
            and isinstance(right, int)
            and op in (operator.mul, operator.pow)
        ):
            try:
                if self.check_size(right):  # type: ignore
                    return None

            except Exception:
                return None

        if op is None:
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

    def visit_Call(self, node: ast.Call):

        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in FUNCS:
                func = FUNCS[func_name]

                args = [self.visit(arg) for arg in node.args]
                if any(arg is None for arg in args):
                    return None

                try:
                    res = func(*args)
                    LOGGER.debug(f"Call {func_name}({args}) -> {res!r}")
                    return res
                except Exception as e:
                    LOGGER.debug(f"Call {func_name} failed: {e}")
                    return None

        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr

            if attr_name in ATTR:
                value = self.visit(node.func.value)

                if value is not None:
                    try:
                        args = [self.visit(arg) for arg in node.args]
                        func = getattr(value, attr_name)
                        result = func(*args)
                        LOGGER.debug(
                            f"Attr call: {type(value).__name__}.{attr_name} -> {result!r}"
                        )
                        return result

                    except Exception:
                        return None

        return None

    def visit_Constant(self, node: ast.Constant):
        return node.value

    def visit_Name(self, node: ast.Name):
        return self.get_name(node.id)

    def visit_List(self, node: ast.List):
        return [self.visit(elt) for elt in node.elts]

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


def safe_eval(node: ast.AST, known_vars: dict | None = None):

    return SafeEval(known_vars).visit(node)
