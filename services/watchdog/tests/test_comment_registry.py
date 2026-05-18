"""Enforce POST_COMMENT_PATHS registry against actual callsites."""

from __future__ import annotations

import ast
from pathlib import Path

from gimle_watchdog.config import POST_COMMENT_PATHS


_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "gimle_watchdog"


class _PostCommentRegistryVisitor(ast.NodeVisitor):
    """Collect enclosing function names for post_issue_comment callsites."""

    def __init__(self, module: str) -> None:
        self.module = module
        self._stack: list[str] = []
        self.found: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if (
            self._stack
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "post_issue_comment"
        ):
            self.found.add(f"{self.module}:{self._stack[-1]}")
        self.generic_visit(node)


def _find_callsites() -> set[str]:
    """Return set of '<module>:<function>' for every post_issue_comment call."""

    found: set[str] = set()
    for py_file in _SRC_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        visitor = _PostCommentRegistryVisitor(py_file.stem)
        visitor.visit(tree)
        found.update(visitor.found)
    return found


def test_post_comment_callsites_match_registry() -> None:
    actual = _find_callsites()
    extra_in_code = actual - POST_COMMENT_PATHS
    extra_in_registry = POST_COMMENT_PATHS - actual
    assert not extra_in_code, (
        "new post_issue_comment callsites not in POST_COMMENT_PATHS: "
        f"{sorted(extra_in_code)}. Update config.POST_COMMENT_PATHS."
    )
    assert not extra_in_registry, (
        "POST_COMMENT_PATHS lists callsites no longer present in code: "
        f"{sorted(extra_in_registry)}. Remove them."
    )


def test_post_comment_paths_is_frozenset() -> None:
    assert isinstance(POST_COMMENT_PATHS, frozenset)
