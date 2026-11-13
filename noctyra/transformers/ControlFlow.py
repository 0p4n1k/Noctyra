from __future__ import annotations

import ast
import builtins
from typing import Any

from noctyra.core import is_symbolic_ref
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
from noctyra.utils.Shared import is_pure_stmt

_BUILTIN_NAMES = frozenset(dir(builtins))


def _strip_redundant_pass(stmts: list[ast.stmt]) -> list[ast.stmt]:
    if len(stmts) <= 1:
        return stmts
    non_pass = [stmt for stmt in stmts if not isinstance(stmt, ast.Pass)]
    if non_pass:
        return non_pass
    return [stmts[0]]


def _contains_break_or_continue(stmts: list[ast.stmt]) -> bool:
    for stmt in stmts:
        for child in ast.walk(stmt):
            if isinstance(child, (ast.Break, ast.Continue)):
                return True
    return False


class ControlFlowSimplifier(BaseTransformer):
    def __init__(self) -> None:
        super().__init__()
        self._defined: set[str] = set()

    def run(
        self,
        node: ast.AST,
        ctx: Any = None,
        max_depth: int = 50,
        max_allocation: int = 100_000,
    ) -> ast.AST:
        self._defined = set(_BUILTIN_NAMES)
        return super().run(node, ctx=ctx, max_depth=max_depth, max_allocation=max_allocation)

    def _def_visit(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        outer_defined = self._defined
        self._defined = set(outer_defined)
        self._defined.add(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local_names = self._collect_func_locals(node)
            self._defined -= local_names
            for arg in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            ):
                self._defined.add(arg.arg)
            if node.args.vararg is not None:
                self._defined.add(node.args.vararg.arg)
            if node.args.kwarg is not None:
                self._defined.add(node.args.kwarg.arg)

        res = super()._def_visit(node)
        self._defined = set(outer_defined)
        self._defined.add(node.name)
        return res

    def visit_Import(self, node: ast.Import) -> Any:
        for name in node.names:
            self._defined.add((name.asname or name.name).split(".")[0])
        return super().visit_Import(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        for alias in node.names:
            if alias.name != "*":
                self._defined.add(alias.asname or alias.name)
        return super().visit_ImportFrom(node)

    def visit_Delete(self, node: ast.Delete) -> Any:
        res = super().visit_Delete(node)
        for t in node.targets:
            for name in self._collect_target_names(t):
                if isinstance(t, ast.Name):
                    self._defined.discard(name)
        return res

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        res = super().visit_AugAssign(node)
        self._defined.update(self._collect_target_names(node.target))
        return res

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        res = super().visit_AnnAssign(node)
        if node.value is not None:
            self._defined.update(self._collect_target_names(node.target))
        return res

    def visit_NamedExpr(self, node: ast.NamedExpr) -> Any:
        res = super().visit_NamedExpr(node)
        self._defined.add(node.target.id)
        return res

    def visit_Assign(self, node: ast.Assign) -> Any:
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Name)
            and node.targets[0].id == node.value.id
            and node.targets[0].id in self._defined
        ):
            LOGGER.debug(
                f"Removed self-assignment: {node.targets[0].id} = {node.value.id}"
            )
            return None
        res = super().visit_Assign(node)
        for t in node.targets:
            if isinstance(t, (ast.Name, ast.Tuple, ast.List)):
                self._defined.update(self._collect_target_names(t))
        return res

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self.generic_visit(node)
        node.body = _strip_redundant_pass(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        res = self._def_visit(node)
        if isinstance(res, ast.FunctionDef):
            res.body = _strip_redundant_pass(res.body)
        return res

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        res = self._def_visit(node)
        if isinstance(res, ast.AsyncFunctionDef):
            res.body = _strip_redundant_pass(res.body)
        return res

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        res = self._def_visit(node)
        if isinstance(res, ast.ClassDef):
            res.body = _strip_redundant_pass(res.body)
        return res

    def visit_If(self, node: ast.If) -> ast.If:
        outer = self._defined
        node.test = self.visit(node.test)
        old_ctx = self.ctx
        assigned = self._collect_assigned_names(node.body) | self._collect_assigned_names(
            node.orelse
        )
        from noctyra.core import Context

        body_ctx = Context(parent=old_ctx)
        self.ctx = body_ctx
        self._defined = set(outer)
        node.body = self._visit_stmt_list(node.body)
        body_defined = self._defined

        else_ctx = Context(parent=old_ctx)
        self.ctx = else_ctx
        self._defined = set(outer)
        node.orelse = self._visit_stmt_list(node.orelse)
        else_defined = self._defined

        self.ctx = old_ctx
        for name in assigned | set(body_ctx.invalidated) | set(else_ctx.invalidated):
            self.ctx.invalidate(name)
        self._defined = outer | (body_defined & else_defined)
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        return node

    def visit_For(self, node: ast.For) -> ast.For:
        outer = self._defined
        super().visit_For(node)
        self._defined = outer
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AsyncFor:
        outer = self._defined
        super().visit_AsyncFor(node)
        self._defined = outer
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        return node

    def visit_With(self, node: ast.With) -> ast.With:
        for item in node.items:
            item.context_expr = self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._defined.update(self._collect_target_names(item.optional_vars))
                for name in self._collect_target_names(item.optional_vars):
                    self.ctx.invalidate(name)
        node.body = self._visit_stmt_list(node.body)
        node.body = _strip_redundant_pass(node.body)
        return node

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AsyncWith:
        for item in node.items:
            item.context_expr = self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._defined.update(self._collect_target_names(item.optional_vars))
                for name in self._collect_target_names(item.optional_vars):
                    self.ctx.invalidate(name)
        node.body = self._visit_stmt_list(node.body)
        node.body = _strip_redundant_pass(node.body)
        return node

    def visit_While(self, node: ast.While) -> Any:
        outer = self._defined
        test_res = self.eval(node.test)
        cff_init = self._peek_cff_init(node)
        self._defined = set(outer)
        super().visit_While(node)
        body_defined = self._defined
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)

        if (
            test_res is not None
            and not is_symbolic_ref(test_res)
            and bool(self.unwrap(test_res))
            and not node.orelse
            and node.body
            and isinstance(node.body[-1], ast.Break)
            and not _contains_break_or_continue(node.body[:-1])
        ):
            self._defined = body_defined
            LOGGER.debug("Unwrapped single-iteration while loop")
            return node.body[:-1]

        self._defined = outer
        unrolled = self._try_unroll_cff(node, cff_init)
        if unrolled is not None:
            return unrolled
        return node

    def _peek_cff_init(self, node: ast.While) -> tuple[str, Any] | None:
        if node.orelse or len(node.body) != 1 or not isinstance(node.body[0], ast.If):
            return None
        first_eq = self._extract_eq_state(node.body[0].test)
        if first_eq is None:
            return None
        state_var = first_eq[0]
        init_entry = self.ctx.get(state_var)
        if init_entry is None:
            return None
        init_raw = init_entry.get()
        if is_symbolic_ref(init_raw):
            return None
        init_state = self.unwrap(init_raw)
        if not isinstance(init_state, (int, str, bytes, bool)):
            return None
        return state_var, init_state

    @staticmethod
    def _extract_eq_state(test: ast.expr) -> tuple[str, Any] | None:
        if (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
        ):
            left, right = test.left, test.comparators[0]
            if (
                isinstance(left, ast.Name)
                and isinstance(right, ast.Constant)
                and isinstance(right.value, (int, str, bytes, bool))
            ):
                return left.id, right.value
            if (
                isinstance(right, ast.Name)
                and isinstance(left, ast.Constant)
                and isinstance(left.value, (int, str, bytes, bool))
            ):
                return right.id, left.value
        return None

    @staticmethod
    def _mentions_name(stmts: list[ast.stmt], name: str) -> bool:
        return any(
            isinstance(child, ast.Name) and child.id == name
            for stmt in stmts
            for child in ast.walk(stmt)
        )

    def _try_unroll_cff(
        self, node: ast.While, cff_init: tuple[str, Any] | None
    ) -> list[ast.stmt] | None:
        from noctyra.core import Context, Variable
        from noctyra.transformers.safe_eval import SafeEval

        if (
            cff_init is None
            or node.orelse
            or len(node.body) != 1
            or not isinstance(node.body[0], ast.If)
        ):
            return None

        state_var, init_state = cff_init

        # Flatten if/elif/else chain
        branches: list[tuple[ast.expr, list[ast.stmt]]] = []
        else_body: list[ast.stmt] = []
        cur_if: ast.If | None = node.body[0]
        while cur_if is not None:
            branches.append((cur_if.test, cur_if.body))
            if len(cur_if.orelse) == 1 and isinstance(cur_if.orelse[0], ast.If):
                cur_if = cur_if.orelse[0]
            else:
                else_body = cur_if.orelse
                cur_if = None

        if len(branches) < 2:
            return None

        cases: dict[Any, tuple[list[ast.stmt], str, Any]] = {}
        for test_expr, b_stmts in branches:
            eq = self._extract_eq_state(test_expr)
            if eq is None or eq[0] != state_var or eq[1] in cases:
                return None
            if not b_stmts:
                return None
            last = b_stmts[-1]
            payload = b_stmts[:-1]
            if _contains_break_or_continue(payload) or self._mentions_name(
                payload, state_var
            ):
                return None
            if (
                isinstance(last, ast.Assign)
                and len(last.targets) == 1
                and isinstance(last.targets[0], ast.Name)
                and last.targets[0].id == state_var
                and isinstance(last.value, ast.Constant)
                and isinstance(last.value.value, (int, str, bytes, bool))
            ):
                cases[eq[1]] = (payload, "next", last.value.value)
            elif isinstance(last, ast.Break):
                cases[eq[1]] = (payload, "break", None)
            elif isinstance(last, (ast.Return, ast.Raise)):
                cases[eq[1]] = (b_stmts, "exit", None)
            else:
                return None

        if else_body and not (
            len(else_body) == 1 and isinstance(else_body[0], (ast.Break, ast.Pass))
        ):
            return None

        unrolled: list[ast.stmt] = []
        visited: set[Any] = set()
        cur_state: Any = init_state
        max_steps = len(cases) + 1

        for _ in range(max_steps):
            loop_ctx = Context([Variable(state_var, cur_state)], self.ctx)
            test_val = SafeEval(
                loop_ctx,
                max_depth=self.max_depth,
                max_allocation=self.max_allocation,
            ).visit(node.test)
            if test_val is None or is_symbolic_ref(test_val):
                return None
            if not bool(self.unwrap(test_val)):
                break

            if cur_state not in cases:
                if else_body and isinstance(else_body[0], ast.Break):
                    break
                return None

            if cur_state in visited:
                return None
            visited.add(cur_state)

            payload, kind, next_val = cases[cur_state]
            unrolled.extend(payload)
            if kind in ("break", "exit"):
                break
            cur_state = next_val
        else:
            return None

        for stmt in unrolled:
            self._defined.update(self._collect_assigned_names([stmt]))
        LOGGER.debug(f"Unrolled CFF while loop on state '{state_var}' ({len(visited)} states)")
        return unrolled

    def _try_body_names_bound(
        self, stmts: list[ast.stmt], pre_defined: set[str]
    ) -> bool:
        bound = set(pre_defined)
        for stmt in stmts:
            for child in ast.walk(stmt):
                if (
                    isinstance(child, ast.Name)
                    and isinstance(child.ctx, ast.Load)
                    and child.id not in bound
                ):
                    return False
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        bound.add(t.id)
        return True

    def visit_Try(self, node: ast.Try) -> Any:
        pre_defined = set(self._defined)
        super().visit_Try(node)
        self._defined = pre_defined
        node.body = _strip_redundant_pass(node.body)
        node.orelse = _strip_redundant_pass(node.orelse)
        node.finalbody = _strip_redundant_pass(node.finalbody)

        if (
            not node.finalbody
            and all(is_pure_stmt(stmt) for stmt in node.body)
            and self._try_body_names_bound(node.body, pre_defined)
        ):
            for stmt in [*node.body, *node.orelse]:
                self._defined.update(self._collect_assigned_names([stmt]))
            LOGGER.debug("Unwrapped pure try block")
            return [*node.body, *node.orelse]

        return node
