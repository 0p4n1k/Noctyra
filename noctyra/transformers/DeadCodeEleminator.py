from __future__ import annotations

import ast
from noctyra.core import is_symbolic_ref
from noctyra.core.Transformer import BaseTransformer
from noctyra.utils import LOGGER
from noctyra.utils.Shared import is_pure_expr


def _collect_loaded_names(node: ast.AST) -> set[str]:
    loaded: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Load, ast.Del)):
            loaded.add(child.id)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            loaded.update(child.names)
        elif isinstance(child, ast.AugAssign):
            base: ast.AST = child.target
            while isinstance(base, (ast.Subscript, ast.Attribute)):
                base = base.value
            if isinstance(base, ast.Name):
                loaded.add(base.id)
    return loaded


def _collect_used_names_in_func(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    used: set[str] = set()
    for stmt in node.body:
        used.update(_collect_loaded_names(stmt))
    return used


def _is_simple_target(t: ast.expr) -> bool:
    if isinstance(t, ast.Name):
        return True
    if isinstance(t, (ast.Tuple, ast.List)):
        return all(_is_simple_target(e) for e in t.elts)
    if isinstance(t, ast.Starred):
        return _is_simple_target(t.value)
    return False


class DeadCodeRemover(BaseTransformer):

    def _is_droppable_expr(self, node: ast.expr) -> bool:
        if is_pure_expr(node, allow_containers=True) or isinstance(node, ast.Lambda):
            return True
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(
                not isinstance(e, ast.Starred) and self._is_droppable_expr(e)
                for e in node.elts
            )
        if isinstance(node, ast.Dict):
            return all(
                k is not None
                and self._is_droppable_expr(k)
                and self._is_droppable_expr(v)
                for k, v in zip(node.keys, node.values)
            )
        return self.eval(node) is not None

    def _prune_unpack_assign(
        self, stmt: ast.Assign, used_names: set[str]
    ) -> ast.Assign | None:
        if len(stmt.targets) != 1 or not isinstance(
            stmt.targets[0], (ast.Tuple, ast.List)
        ):
            return stmt

        tgt = stmt.targets[0]
        if _is_simple_target(tgt):
            target_names = self._collect_target_names(tgt)
            if not (target_names & used_names) and self._is_droppable_expr(stmt.value):
                LOGGER.debug("Removed dead unpacking assignment")
                return None

        if (
            isinstance(stmt.value, (ast.Tuple, ast.List))
            and len(tgt.elts) == len(stmt.value.elts)
            and not any(isinstance(e, ast.Starred) for e in tgt.elts)
            and not any(isinstance(e, ast.Starred) for e in stmt.value.elts)
        ):
            kept: list[tuple[ast.expr, ast.expr]] = []
            for t, v in zip(tgt.elts, stmt.value.elts):
                if (
                    _is_simple_target(t)
                    and not (self._collect_target_names(t) & used_names)
                    and self._is_droppable_expr(v)
                ):
                    LOGGER.debug("Pruned dead target in unpacking assignment")
                    continue
                kept.append((t, v))

            if not kept:
                return None
            if len(kept) == len(tgt.elts):
                return stmt
            if len(kept) == 1:
                t0, v0 = kept[0]
                return ast.copy_location(ast.Assign(targets=[t0], value=v0), stmt)
            new_tgt = ast.copy_location(
                type(tgt)(elts=[t for t, _ in kept], ctx=tgt.ctx), tgt
            )
            new_val = ast.copy_location(
                type(stmt.value)(elts=[v for _, v in kept], ctx=stmt.value.ctx),
                stmt.value,
            )
            return ast.copy_location(
                ast.Assign(targets=[new_tgt], value=new_val), stmt
            )

        return stmt

    def _ensure_nonempty_bodies(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.ExceptHandler)):
                if not child.body:
                    child.body = [ast.Pass()]
            elif isinstance(child, ast.Try):
                if not child.body:
                    child.body = [ast.Pass()]

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self.generic_visit(node)
        self._ensure_nonempty_bodies(node)

        # Collect all loaded/referenced names outside of import statements
        used_names: set[str] = set()
        for stmt in node.body:
            if not isinstance(stmt, (ast.Import, ast.ImportFrom)):
                used_names.update(_collect_loaded_names(stmt))

        pruned_body: list[ast.stmt] = []
        changed_unpack = False
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], (ast.Tuple, ast.List))
            ):
                pruned = self._prune_unpack_assign(stmt, used_names)
                if pruned is None:
                    changed_unpack = True
                    continue
                if pruned is not stmt:
                    changed_unpack = True
                pruned_body.append(pruned)
            else:
                pruned_body.append(stmt)

        if changed_unpack:
            used_names = set()
            for stmt in pruned_body:
                if not isinstance(stmt, (ast.Import, ast.ImportFrom)):
                    used_names.update(_collect_loaded_names(stmt))

        new_body: list[ast.stmt] = []
        for stmt in pruned_body:
            if isinstance(stmt, ast.Import):
                kept_aliases = [
                    alias
                    for alias in stmt.names
                    if (alias.asname or alias.name.split(".")[0]) in used_names
                ]
                if not kept_aliases:
                    LOGGER.debug(f"Removed unused import: {ast.unparse(stmt)}")
                    continue
                stmt.names = kept_aliases
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module == "__future__" or any(
                    alias.name == "*" for alias in stmt.names
                ):
                    new_body.append(stmt)
                    continue
                kept_aliases = [
                    alias
                    for alias in stmt.names
                    if (alias.asname or alias.name) in used_names
                ]
                if not kept_aliases:
                    LOGGER.debug(f"Removed unused from-import: {ast.unparse(stmt)}")
                    continue
                stmt.names = kept_aliases
            new_body.append(stmt)

        node.body = new_body
        return node

    def visit_If(self, node: ast.If):
        super().visit_If(node)

        test_res = self.eval(node.test)
        if test_res is None or is_symbolic_ref(test_res):
            return node

        test_value = self.unwrap(test_res)
        if bool(test_value):
            return node.body
        return node.orelse

    def visit_While(self, node: ast.While):
        super().visit_While(node)

        test_res = self.eval(node.test)
        if (
            test_res is not None
            and not is_symbolic_ref(test_res)
            and not bool(self.unwrap(test_res))
        ):
            LOGGER.debug("Removed dead while loop")
            return node.orelse

        return node

    def _clean_stmt_list(
        self, stmts: list[ast.stmt], used_names: set[str], allow_empty: bool = False
    ) -> list[ast.stmt]:
        truncated: list[ast.stmt] = []
        for stmt in stmts:
            truncated.append(stmt)
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                break

        cleaned: list[ast.stmt] = []
        for stmt in truncated:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id not in used_names
                and is_pure_expr(stmt.value, allow_containers=True)
            ):
                LOGGER.debug(f"Removed dead local assignment: {stmt.targets[0].id}")
                continue
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], (ast.Tuple, ast.List))
            ):
                pruned = self._prune_unpack_assign(stmt, used_names)
                if pruned is None:
                    continue
                stmt = pruned
            if isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While)):
                stmt.body = self._clean_stmt_list(stmt.body, used_names)
                if stmt.orelse:
                    stmt.orelse = self._clean_stmt_list(
                        stmt.orelse, used_names, allow_empty=True
                    )
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                stmt.body = self._clean_stmt_list(stmt.body, used_names)
            elif isinstance(stmt, ast.Try):
                stmt.body = self._clean_stmt_list(stmt.body, used_names)
                for handler in stmt.handlers:
                    handler.body = self._clean_stmt_list(handler.body, used_names)
                if stmt.orelse:
                    stmt.orelse = self._clean_stmt_list(
                        stmt.orelse, used_names, allow_empty=True
                    )
                if stmt.finalbody:
                    stmt.finalbody = self._clean_stmt_list(
                        stmt.finalbody, used_names, allow_empty=True
                    )
            cleaned.append(stmt)

        if not cleaned and not allow_empty:
            cleaned = [ast.Pass()]
        return cleaned

    def _clean_func_body(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        self.generic_visit(node)

        used_names = _collect_used_names_in_func(node)
        node.body = self._clean_stmt_list(node.body, used_names)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        return self._clean_func_body(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self._clean_func_body(node)
