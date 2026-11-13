import ast
import copy
from typing import Any

from noctyra.core import Context, ImportSymbol, LambdaType, is_symbolic_ref, to_node
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import COMP_OPS, IMMUTABLE_TYPES, LOGGER
from noctyra.utils.Shared import is_pure_expr

_SCOPE_BOUNDARY_NODES = (
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


def _contains_named_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.NamedExpr):
        return True
    if isinstance(node, _SCOPE_BOUNDARY_NODES):
        return False
    return any(_contains_named_expr(child) for child in ast.iter_child_nodes(node))


def _has_unhashable_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.Tuple):
        return any(_has_unhashable_literal(e) for e in node.elts)
    return False


class _NamedExprExtractor(ast.NodeTransformer):
    def __init__(self, owner: "ConditionSimplifier") -> None:
        self._owner = owner

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        return node

    def visit_SetComp(self, node: ast.SetComp) -> ast.AST:
        return node

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        return node

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.AST:
        return node

    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:
        clean_val = self.visit(node.value)
        self._owner._hoist_named_expr(node, clean_val)
        return ast.copy_location(
            ast.Name(id=node.target.id, ctx=ast.Load()), node
        )


class ConditionSimplifier(BaseTransformer):
    def __init__(self) -> None:
        super().__init__()
        self._hoist_stack: list[list[ast.stmt] | None] = []

    def _can_hoist(self) -> bool:
        return bool(self._hoist_stack and self._hoist_stack[-1] is not None)

    def _hoist_named_expr(self, node: ast.NamedExpr, clean_val: ast.expr) -> None:
        buf = self._hoist_stack[-1]
        assert buf is not None
        assign = ast.copy_location(
            ast.Assign(
                targets=[ast.Name(id=node.target.id, ctx=ast.Store())],
                value=copy.deepcopy(clean_val),
            ),
            node,
        )
        ast.fix_missing_locations(assign)
        buf.append(assign)
        plan = self._plan_bind(
            ast.Name(id=node.target.id, ctx=ast.Store()), clean_val
        )
        self._apply_bind_plan(*plan)

    def _extract_named_exprs(self, node: ast.expr) -> ast.expr:
        return _NamedExprExtractor(self).visit(node)

    def _eval_truthiness(self, node: ast.expr) -> bool | None:
        res = self.eval(node)
        if res is not None:
            if isinstance(res, (ImportSymbol, LambdaType)):
                return True
            return bool(self.unwrap(res))

        if isinstance(node, ast.Name):
            import builtins

            target_name = self.ctx.remap_get(node.id) or node.id
            if self._is_builtin_usable(target_name) and hasattr(
                builtins, target_name
            ):
                return bool(getattr(builtins, target_name))

        if isinstance(node, ast.Lambda):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self._eval_truthiness(node.operand)
            return (not inner) if inner is not None else None
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if isinstance(node, ast.Set) and any(
                _has_unhashable_literal(e) for e in node.elts
            ):
                return None
            if not node.elts:
                return False
            if any(not isinstance(e, ast.Starred) for e in node.elts):
                return True
            return None
        if isinstance(node, ast.Dict):
            if any(_has_unhashable_literal(k) for k in node.keys):
                return None
            if not node.keys:
                return False
            if any(k is not None for k in node.keys):
                return True
            return None
        if isinstance(node, ast.NamedExpr):
            return self._eval_truthiness(node.value)
        return None

    def _is_foldable_pure(self, node: ast.expr) -> bool:
        if is_pure_expr(node, allow_containers=True) or isinstance(node, ast.Lambda):
            return True
        if isinstance(node, ast.NamedExpr):
            return self._is_foldable_pure(node.value)
        if isinstance(node, ast.UnaryOp):
            return self._is_foldable_pure(node.operand)
        if isinstance(node, ast.BoolOp):
            return all(self._is_foldable_pure(v) for v in node.values)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(
                not isinstance(e, ast.Starred) and self._is_foldable_pure(e)
                for e in node.elts
            )
        if isinstance(node, ast.Dict):
            return all(
                k is not None
                and self._is_foldable_pure(k)
                and self._is_foldable_pure(v)
                for k, v in zip(node.keys, node.values)
            )
        return self.eval(node) is not None

    def _visit_stmt_with_hoist(self, node: ast.stmt, visit_fn: Any) -> Any:
        self._hoist_stack.append([])
        try:
            res = visit_fn(node)
        finally:
            hoisted = self._hoist_stack.pop()
        if hoisted:
            if isinstance(res, list):
                return [*hoisted, *res]
            return [*hoisted, res]
        return res

    def visit_Expr(self, node: ast.Expr) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Assign(self, node: ast.Assign) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_Assign)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_AnnAssign)

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_AugAssign)

    def visit_Return(self, node: ast.Return) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Raise(self, node: ast.Raise) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Assert(self, node: ast.Assert) -> Any:
        return self._visit_stmt_with_hoist(node, super().generic_visit)

    def visit_Delete(self, node: ast.Delete) -> Any:
        return self._visit_stmt_with_hoist(node, super().visit_Delete)

    def visit_If(self, node: ast.If) -> Any:
        self._hoist_stack.append([])
        try:
            node.test = self.visit(node.test)
        finally:
            hoisted = self._hoist_stack.pop()

        # Visit body/orelse using BaseTransformer's context handling without re-visiting test
        old_ctx = self.ctx
        assigned = self._collect_assigned_names(
            node.body
        ) | self._collect_assigned_names(node.orelse)

        from noctyra.core import Context

        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self._visit_stmt_list(node.body)

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)

        if hoisted:
            return [*hoisted, node]
        return node

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> Any:
        assigned = self._collect_assigned_names(
            node.body
        ) | self._collect_assigned_names(node.orelse)

        hoisted: list[ast.stmt] | None = None
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._hoist_stack.append([])
            try:
                node.iter = self.visit(node.iter)
            finally:
                hoisted = self._hoist_stack.pop()
            assigned.update(self._collect_target_names(node.target))

        for name in assigned:
            self.ctx.invalidate(name)

        if isinstance(node, ast.While):
            self._hoist_stack.append(None)
            try:
                node.test = self.visit(node.test)
            finally:
                self._hoist_stack.pop()

        from noctyra.core import Context

        old_ctx = self.ctx
        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        node.body = self._visit_stmt_list(node.body)

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        node.orelse = self._visit_stmt_list(node.orelse)

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)

        if hoisted:
            return [*hoisted, node]
        return node

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._hoist_stack.append(None)
        try:
            return self.generic_visit(node)
        finally:
            self._hoist_stack.pop()

    def _visit_comp(self, node: ast.AST) -> ast.AST:
        self._hoist_stack.append(None)
        try:
            return super()._visit_comp(node)
        finally:
            self._hoist_stack.pop()

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._is_foldable_pure(node.operand):
            truthy = self._eval_truthiness(node.operand)
            if truthy is not None:
                if _contains_named_expr(node.operand):
                    if not self._can_hoist():
                        return node
                    self._extract_named_exprs(node.operand)
                return ast.copy_location(ast.Constant(value=not truthy), node)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        is_and = isinstance(node.op, ast.And)
        remaining: list[ast.expr] = []
        last_const: tuple[bool, object] | None = None
        last_surviving: ast.expr | None = None

        old_ctx = self.ctx
        sub_ctx: Context | None = None
        walrus_targets: set[str] = set()

        try:
            for idx, raw_val in enumerate(node.values):
                if remaining:
                    if sub_ctx is None:
                        sub_ctx = Context(parent=old_ctx)
                    if isinstance(raw_val, ast.NamedExpr):
                        walrus_targets.add(raw_val.target.id)
                    self._collect_nested_walrus(raw_val, walrus_targets)
                    self.ctx = sub_ctx
                    self._hoist_stack.append(None)
                    try:
                        val = self.visit(raw_val)
                    finally:
                        self._hoist_stack.pop()
                else:
                    val = self.visit(raw_val)

                if not self._is_foldable_pure(val):
                    remaining.append(val)
                    last_const = None
                    last_surviving = None
                    continue

                truthy = self._eval_truthiness(val)
                if truthy is None:
                    remaining.append(val)
                    last_const = None
                    last_surviving = None
                    continue

                if _contains_named_expr(val) and (remaining or not self._can_hoist()):
                    remaining.append(val)
                    last_const = None
                    last_surviving = None
                    continue

                if _contains_named_expr(val):
                    val = self._extract_named_exprs(val)

                res = self.eval(val)
                unwrapped: Any = None
                is_const = False
                if res is not None and not is_symbolic_ref(res):
                    unwrapped = self.unwrap(res)
                    is_const = isinstance(unwrapped, IMMUTABLE_TYPES)

                short_circuit = (not truthy) if is_and else truthy
                is_last = idx == len(node.values) - 1

                if short_circuit or (remaining and is_last):
                    if not remaining and is_const:
                        return ast.copy_location(ast.Constant(value=unwrapped), node)
                    const_node: ast.expr = (
                        ast.copy_location(ast.Constant(value=unwrapped), val)
                        if is_const
                        else val
                    )
                    remaining.append(const_node)
                    last_const = None
                    last_surviving = None
                    if short_circuit:
                        break
                    continue

                last_const = (is_const, unwrapped)
                last_surviving = val
        finally:
            self.ctx = old_ctx

        if sub_ctx is not None:
            for name in walrus_targets | set(sub_ctx.invalidated):
                self.ctx.invalidate(name)

        if not remaining:
            if last_const is not None and last_const[0]:
                return ast.copy_location(ast.Constant(value=last_const[1]), node)  # type: ignore[arg-type]
            if last_surviving is not None:
                return ast.copy_location(last_surviving, node)

        if len(remaining) == 1:
            return remaining[0]

        if remaining:
            return ast.copy_location(ast.BoolOp(op=node.op, values=remaining), node)

        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        left_res = self.eval(node.left)
        if left_res is None or is_symbolic_ref(left_res):
            return node

        left = self.unwrap(left_res)
        results = []

        for op, comparator in zip(node.ops, node.comparators):
            right_res = self.eval(comparator)
            if right_res is None or is_symbolic_ref(right_res):
                return node

            right = self.unwrap(right_res)

            op_type = type(op)
            if op_type in COMP_OPS:
                try:
                    result = COMP_OPS[op_type](left, right)
                    results.append(result)
                    left = right
                except Exception as e:
                    LOGGER.debug(f"Comparison failed: {e}")
                    return node

            else:
                return node

        if results and all(i is not None for i in results):
            final_res = all(results)
            LOGGER.debug(f"Simplified comparison: {final_res}")
            return ast.Constant(value=final_res)

        return node

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        node.test = self.visit(node.test)

        if self._is_foldable_pure(node.test):
            test_truth = self._eval_truthiness(node.test)
            if test_truth is not None:
                if _contains_named_expr(node.test):
                    if self._can_hoist():
                        self._extract_named_exprs(node.test)
                        kept = node.body if test_truth else node.orelse
                        return ast.copy_location(self.visit(kept), node)
                else:
                    kept = node.body if test_truth else node.orelse
                    return ast.copy_location(self.visit(kept), node)

        old_ctx = self.ctx
        walrus_targets: set[str] = set()
        for branch in (node.body, node.orelse):
            if isinstance(branch, ast.NamedExpr):
                walrus_targets.add(branch.target.id)
            self._collect_nested_walrus(branch, walrus_targets)

        self._hoist_stack.append(None)
        try:
            body_ctx = Context(parent=old_ctx)
            self.ctx = body_ctx
            node.body = self.visit(node.body)

            else_ctx = Context(parent=old_ctx)
            self.ctx = else_ctx
            node.orelse = self.visit(node.orelse)
        finally:
            self.ctx = old_ctx
            self._hoist_stack.pop()

        for name in walrus_targets | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)

        result_res = self.eval(node)
        if result_res is not None and not is_symbolic_ref(result_res):
            folded = to_node(self.unwrap(result_res))
            if folded is not None:
                return ast.copy_location(folded, node)

        return node
