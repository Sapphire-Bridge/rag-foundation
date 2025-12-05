"""Check that admin mutation routes include audit logging."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


MUTATING_METHODS = {"post", "put", "delete", "patch"}


def _decorator_is_mutation(dec: ast.AST) -> bool:
    if not isinstance(dec, ast.Call):
        return False
    func = dec.func
    return isinstance(func, ast.Attribute) and func.attr in MUTATING_METHODS


def _calls_require_admin(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id != "Depends":
        return False
    for arg in node.args:
        if isinstance(arg, ast.Name) and arg.id == "require_admin":
            return True
        if isinstance(arg, ast.Attribute) and arg.attr == "require_admin":
            return True
    return False


def _function_uses_require_admin(func: ast.AST) -> bool:
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    defaults: Iterable[ast.AST] = list(func.args.defaults or []) + list(func.args.kw_defaults or [])
    return any(_calls_require_admin(d) for d in defaults if d is not None)


def _function_has_admin_audit(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "record_admin_action":
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == "record_admin_action":
                return True
    return False


def _iter_admin_mutations(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_decorator_is_mutation(dec) for dec in node.decorator_list):
            continue
        if not _function_uses_require_admin(node):
            continue
        yield node


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    routes_dir = repo_root / "backend" / "app" / "routes"
    missing: list[str] = []

    for route_file in sorted(routes_dir.glob("*.py")):
        try:
            tree = ast.parse(route_file.read_text())
        except SyntaxError as exc:
            print(f"❌ Syntax error in {route_file}: {exc}")
            return 1

        for func in _iter_admin_mutations(tree):
            if not _function_has_admin_audit(func):
                missing.append(f"{route_file.relative_to(repo_root)}:{func.lineno} ({func.name})")

    if missing:
        print("⚠️  Admin mutations missing record_admin_action:")
        for entry in missing:
            print(f" - {entry}")
        return 1

    print("✅ Admin mutations include record_admin_action")
    return 0


if __name__ == "__main__":
    sys.exit(main())
