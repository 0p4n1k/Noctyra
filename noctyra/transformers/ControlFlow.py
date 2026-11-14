from __future__ import annotations

import ast
import builtins
import copy
from typing import Any

from noctyra.core import Context, Variable, is_symbolic_ref, to_node
from noctyra.core.Transformer import BaseTransformer
from noctyra.transformers.safe_eval import SafeEval
from noctyra.utils import BIN_OPS, LOGGER
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
        if cff_init is None:
            bounded = self._try_eval_bounded_while(node)
            if bounded is not None:
                return bounded

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

    @classmethod
    def _is_simulatable_stmts(cls, stmts: list[ast.stmt]) -> bool:
        for stmt in stmts:
            if isinstance(
                stmt,
                (ast.Assign, ast.AugAssign, ast.Expr, ast.Break, ast.Continue, ast.Pass),
            ):
                continue
            if isinstance(stmt, ast.If):
                if not cls._is_simulatable_stmts(
                    stmt.body
                ) or not cls._is_simulatable_stmts(stmt.orelse):
                    return False
                continue
            if isinstance(stmt, (ast.While, ast.For)):
                if not cls._is_simulatable_stmts(
                    stmt.body
                ) or not cls._is_simulatable_stmts(stmt.orelse):
                    return False
                continue
            return False
        return True

    def _try_eval_bounded_while(self, node: ast.While) -> list[ast.stmt] | None:
        if not self._is_simulatable_stmts([node]):
            return None

        sim_ctx = Context([], self.ctx)
        evaluator = SafeEval(
            sim_ctx,
            max_depth=self.max_depth,
            max_allocation=self.max_allocation,
        )
        max_iters = min(self.max_allocation, 100_000)
        max_steps = min(self.max_allocation * 16, 1_000_000)
        num_limit = max(self.max_allocation, 2**63 - 1)
        iters = 0
        steps = 0
        loop_depth = 0
        modified_order: list[str] = []
        modified_set: set[str] = set()
        local_vars: set[str] = set()

        def within_sim_bounds(val: Any) -> bool:
            if is_symbolic_ref(val):
                return False
            if isinstance(
                val, (str, bytes, bytearray, list, dict, set, tuple, range)
            ):
                try:
                    if len(val) > self.max_allocation:
                        return False
                except OverflowError:
                    return False
                if isinstance(val, (list, tuple, set)):
                    return all(within_sim_bounds(x) for x in val)
                if isinstance(val, dict):
                    return all(
                        within_sim_bounds(k) and within_sim_bounds(v)
                        for k, v in val.items()
                    )
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                if val > num_limit or val < -num_limit:
                    return False
            return True

        def has_outer_alias(name: str, val: Any) -> bool:
            if not isinstance(val, (list, dict, set, bytearray)):
                return False
            ctx_ptr: Context | None = self.ctx
            while ctx_ptr is not None:
                for var in ctx_ptr.vars:
                    if var.name != name and self.unwrap(var.get()) is val:
                        return True
                ctx_ptr = ctx_ptr.parent
            return False

        def mark_modified(name: str) -> None:
            if name not in modified_set:
                modified_set.add(name)
                modified_order.append(name)

        def ensure_local_value(name: str, *, for_mutation: bool) -> tuple[bool, Any]:
            if name in local_vars:
                entry = sim_ctx.get(name)
                if entry is None:
                    return False, None
                return True, self.unwrap(entry.get())
            entry = self.ctx.get(name)
            if entry is None:
                return False, None
            val = self.unwrap(entry.get())
            if is_symbolic_ref(val):
                return False, None
            if for_mutation:
                if has_outer_alias(name, val):
                    return False, None
                if isinstance(val, (list, dict, set, bytearray)):
                    val = copy.deepcopy(val)
                sim_ctx.set(name, val)
                local_vars.add(name)
            return True, val

        def set_local(name: str, val: Any) -> bool:
            if not within_sim_bounds(val):
                return False
            sim_ctx.set(name, val)
            local_vars.add(name)
            mark_modified(name)
            return True

        def eval_expr(expr: ast.expr) -> tuple[bool, Any]:
            res = evaluator.visit(expr)
            if res is None or is_symbolic_ref(res):
                return False, None
            val = self.unwrap(res)
            if not within_sim_bounds(val):
                return False, None
            return True, val

        def resolve_subscript_chain(
            target: ast.AST,
        ) -> tuple[str, list[Any]] | None:
            slices: list[ast.expr] = []
            cur: ast.AST = target
            while isinstance(cur, ast.Subscript):
                slices.append(cur.slice)
                cur = cur.value
            if not isinstance(cur, ast.Name):
                return None
            keys: list[Any] = []
            for s_node in reversed(slices):
                ok, key = eval_expr(s_node)
                if not ok:
                    return None
                keys.append(key)
            return cur.id, keys

        def bind_target(target: ast.AST, val: Any) -> bool:
            if isinstance(target, ast.Name):
                return set_local(target.id, val)
            if isinstance(target, (ast.Tuple, ast.List)):
                if any(isinstance(e, ast.Starred) for e in target.elts):
                    return False
                if not isinstance(
                    val, (tuple, list, str, bytes, bytearray, range, set, dict)
                ):
                    return False
                seq = list(val)
                if len(target.elts) != len(seq):
                    return False
                return all(bind_target(t, item) for t, item in zip(target.elts, seq))
            if isinstance(target, ast.Subscript):
                chain = resolve_subscript_chain(target)
                if chain is None:
                    return False
                root_name, keys = chain
                ok, container = ensure_local_value(root_name, for_mutation=True)
                if not ok:
                    return False
                try:
                    for key in keys[:-1]:
                        container = container[key]
                    if not isinstance(container, (list, dict, bytearray)):
                        return False
                    container[keys[-1]] = val
                except Exception:
                    return False
                if not within_sim_bounds(
                    self.unwrap(sim_ctx.get(root_name).get())
                ):
                    return False
                mark_modified(root_name)
                return True
            return False

        def exec_mutating_call(call: ast.Call) -> bool | None:
            """Return True if handled as mutating call, False if not a mutating call, None on abort."""
            if (
                not isinstance(call.func, ast.Attribute)
                or call.func.attr
                not in ("append", "extend", "insert", "pop", "reverse", "clear")
                or call.keywords
                or any(isinstance(a, ast.Starred) for a in call.args)
            ):
                return False
            recv = call.func.value
            if isinstance(recv, ast.Name):
                root_name = recv.id
                keys: list[Any] = []
            elif isinstance(recv, ast.Subscript):
                chain = resolve_subscript_chain(recv)
                if chain is None:
                    return None
                root_name, keys = chain
            else:
                return False

            ok, obj = ensure_local_value(root_name, for_mutation=True)
            if not ok:
                return None
            try:
                for key in keys:
                    obj = obj[key]
            except Exception:
                return None

            if not isinstance(obj, (list, bytearray)):
                return None

            args: list[Any] = []
            for arg_node in call.args:
                ok_arg, arg_val = eval_expr(arg_node)
                if not ok_arg:
                    return None
                args.append(arg_val)

            attr = call.func.attr
            try:
                if attr == "append":
                    if len(args) != 1 or len(obj) >= self.max_allocation:
                        return None
                    obj.append(args[0])
                elif attr == "extend":
                    if len(args) != 1:
                        return None
                    ext = args[0]
                    if not isinstance(
                        ext, (list, tuple, str, bytes, bytearray, range, set, dict)
                    ):
                        return None
                    if len(obj) + len(ext) > self.max_allocation:
                        return None
                    ext_val: Any = ext
                    obj.extend(ext_val)
                elif attr == "insert":
                    if len(args) != 2 or len(obj) >= self.max_allocation:
                        return None
                    obj.insert(args[0], args[1])
                elif attr == "pop":
                    if len(args) > 1:
                        return None
                    obj.pop(*args)
                elif attr == "reverse":
                    if args:
                        return None
                    obj.reverse()
                elif attr == "clear":
                    if args:
                        return None
                    obj.clear()
            except Exception:
                return None

            mark_modified(root_name)
            return True

        def exec_block(stmts: list[ast.stmt]) -> str | None:
            for stmt in stmts:
                sig = exec_stmt(stmt)
                if sig is None:
                    return None
                if sig != "normal":
                    return sig
            return "normal"

        def exec_stmt(stmt: ast.stmt) -> str | None:
            nonlocal steps, iters, loop_depth
            steps += 1
            if steps > max_steps:
                return None

            if isinstance(stmt, ast.Pass):
                return "normal"
            if isinstance(stmt, ast.Break):
                return "break"
            if isinstance(stmt, ast.Continue):
                return "continue"

            if isinstance(stmt, ast.Assign):
                ok, rhs_val = eval_expr(stmt.value)
                if not ok:
                    return None
                if (
                    len(stmt.targets) > 1
                    and isinstance(rhs_val, (list, dict, set, bytearray))
                ):
                    return None
                for target in stmt.targets:
                    if not bind_target(target, rhs_val):
                        return None
                return "normal"

            if isinstance(stmt, ast.AugAssign):
                op_fn = BIN_OPS.get(type(stmt.op))
                if op_fn is None:
                    return None
                ok_rhs, rhs_val = eval_expr(stmt.value)
                if not ok_rhs:
                    return None
                if isinstance(stmt.target, ast.Name):
                    ok_cur, cur_val = ensure_local_value(
                        stmt.target.id, for_mutation=True
                    )
                    if not ok_cur:
                        return None
                    try:
                        new_val = op_fn(cur_val, rhs_val)
                    except Exception:
                        return None
                    if not set_local(stmt.target.id, new_val):
                        return None
                    return "normal"
                if isinstance(stmt.target, ast.Subscript):
                    chain = resolve_subscript_chain(stmt.target)
                    if chain is None:
                        return None
                    root_name, keys = chain
                    ok_cur, container = ensure_local_value(
                        root_name, for_mutation=True
                    )
                    if not ok_cur:
                        return None
                    try:
                        for key in keys[:-1]:
                            container = container[key]
                        if not isinstance(container, (list, dict, bytearray)):
                            return None
                        new_elem = op_fn(container[keys[-1]], rhs_val)
                        if not within_sim_bounds(new_elem):
                            return None
                        container[keys[-1]] = new_elem
                    except Exception:
                        return None
                    if not within_sim_bounds(
                        self.unwrap(sim_ctx.get(root_name).get())
                    ):
                        return None
                    mark_modified(root_name)
                    return "normal"
                return None

            if isinstance(stmt, ast.Expr):
                if isinstance(stmt.value, ast.Call):
                    mut_res = exec_mutating_call(stmt.value)
                    if mut_res is None:
                        return None
                    if mut_res:
                        return "normal"
                ok, _ = eval_expr(stmt.value)
                return "normal" if ok else None

            if isinstance(stmt, ast.If):
                ok, cond = eval_expr(stmt.test)
                if not ok:
                    return None
                branch = stmt.body if bool(cond) else stmt.orelse
                return exec_block(branch)

            if isinstance(stmt, ast.While):
                if loop_depth >= self.max_depth:
                    return None
                loop_depth += 1
                try:
                    broke = False
                    while True:
                        iters += 1
                        if iters > max_iters:
                            return None
                        ok, cond = eval_expr(stmt.test)
                        if not ok:
                            return None
                        if not bool(cond):
                            break
                        sig = exec_block(stmt.body)
                        if sig is None:
                            return None
                        if sig == "break":
                            broke = True
                            break
                    if not broke and stmt.orelse:
                        sig_else = exec_block(stmt.orelse)
                        if sig_else is None or sig_else != "normal":
                            return sig_else
                    return "normal"
                finally:
                    loop_depth -= 1

            if isinstance(stmt, ast.For):
                if loop_depth >= self.max_depth:
                    return None
                ok, iterable = eval_expr(stmt.iter)
                if not ok or not isinstance(
                    iterable, (list, tuple, str, bytes, bytearray, range, set, dict)
                ):
                    return None
                loop_depth += 1
                try:
                    broke = False
                    for item in iterable:
                        iters += 1
                        if iters > max_iters:
                            return None
                        if not bind_target(stmt.target, item):
                            return None
                        sig = exec_block(stmt.body)
                        if sig is None:
                            return None
                        if sig == "break":
                            broke = True
                            break
                    if not broke and stmt.orelse:
                        sig_else = exec_block(stmt.orelse)
                        if sig_else is None or sig_else != "normal":
                            return sig_else
                    return "normal"
                finally:
                    loop_depth -= 1

            return None

        if exec_stmt(node) != "normal":
            return None

        result_stmts: list[ast.stmt] = []
        final_values: list[tuple[str, Any]] = []
        for name in modified_order:
            entry = sim_ctx.get(name)
            if entry is None:
                return None
            val = self.unwrap(entry.get())
            if not within_sim_bounds(val):
                return None
            val_node = to_node(val)
            if val_node is None:
                return None
            assign = ast.Assign(
                targets=[ast.Name(id=name, ctx=ast.Store())],
                value=val_node,
            )
            ast.copy_location(assign, node)
            ast.fix_missing_locations(assign)
            result_stmts.append(assign)
            final_values.append((name, val))

        for name, val in final_values:
            self.ctx.set(name, val)
            self._defined.add(name)

        LOGGER.debug(
            f"Evaluated bounded while loop ({iters} iters, {steps} steps, {len(final_values)} vars)"
        )
        if not result_stmts:
            return [ast.copy_location(ast.Pass(), node)]
        return result_stmts

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
