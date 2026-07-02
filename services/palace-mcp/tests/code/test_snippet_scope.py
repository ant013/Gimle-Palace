"""Unit tests for snippet_scope multi-document assembly (no live graph)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from palace_mcp.code import snippet_scope as ss


def _snip(
    source: str,
    *,
    truncated: bool = False,
    truncated_lines: int = 0,
    truncated_reason: str | None = None,
    total_lines: int = 1,
) -> Any:
    return SimpleNamespace(
        source=source,
        start_line=1,
        end_line=source.count("\n") + 1,
        total_lines=total_lines,
        truncated=truncated,
        truncated_lines=truncated_lines,
        truncated_reason=truncated_reason,
        byte_count=len(source.encode()),
    )


def test_plan_type_scope_swift_type_stays_type() -> None:
    plan = ss.plan_type_scope("class", "Foo.swift")
    assert plan.effective_scope == "type" and not plan.scope_downgraded


def test_plan_type_scope_member_downgrades_to_file() -> None:
    plan = ss.plan_type_scope("method", "Foo.swift")
    assert plan.effective_scope == "file" and plan.scope_downgraded
    assert "member" in (plan.downgrade_reason or "")


def test_plan_type_scope_non_swift_downgrades_to_file() -> None:
    plan = ss.plan_type_scope("class", "Foo.kt")
    assert plan.effective_scope == "file" and plan.scope_downgraded
    assert "Swift" in (plan.downgrade_reason or "")


def test_order_type_files_declaration_first_rest_sorted() -> None:
    roles = ss.order_type_files(
        "Foo.swift", ["Zzz+Ext.swift", "Foo.swift", "Aaa+Ext.swift"]
    )
    assert roles[0] == ("Foo.swift", "declaration")
    assert roles[1:] == [("Aaa+Ext.swift", "extension"), ("Zzz+Ext.swift", "extension")]


def test_build_documents_happy_path() -> None:
    def fake_resolve(**_: Any) -> Any:
        return _snip("body"), None, None

    docs, rollup = ss.build_documents(
        [("A.swift", "declaration"), ("B.swift", "extension")],
        project="p",
        repo_path=None,
        commit_sha=None,
        freshness=None,
        resolve=fake_resolve,
    )
    assert len(docs) == 2
    assert rollup["documents_failed"] == 0
    assert rollup["documents_truncated"] == 0
    assert rollup["dropped_files"] == []
    assert docs[0].role == "declaration" and docs[0].source == "body"


def test_build_documents_captures_per_doc_failure() -> None:
    def fake_resolve(*, file_path: str, **_: Any) -> Any:
        if file_path == "B.swift":
            return None, "missing_source_file", "gone"
        return _snip("ok"), None, None

    docs, rollup = ss.build_documents(
        [("A.swift", "declaration"), ("B.swift", "extension")],
        project="p",
        repo_path=None,
        commit_sha=None,
        freshness=None,
        resolve=fake_resolve,
    )
    assert rollup["documents_failed"] == 1
    failed = [d for d in docs if d.error_code == "missing_source_file"]
    assert failed and failed[0].source is None


def test_build_documents_counts_truncation() -> None:
    def fake_resolve(**_: Any) -> Any:
        return (
            _snip("x", truncated=True, truncated_lines=50, truncated_reason="lines"),
            None,
            None,
        )

    _, rollup = ss.build_documents(
        [("A.swift", "declaration")],
        project="p",
        repo_path=None,
        commit_sha=None,
        freshness=None,
        resolve=fake_resolve,
    )
    assert rollup["documents_truncated"] == 1


def test_build_documents_file_count_cap_lists_dropped() -> None:
    files = [(f"F{i}.swift", "extension") for i in range(ss._MAX_TYPE_FILES + 3)]

    def fake_resolve(**_: Any) -> Any:
        return _snip("y"), None, None

    docs, rollup = ss.build_documents(
        files,
        project="p",
        repo_path=None,
        commit_sha=None,
        freshness=None,
        resolve=fake_resolve,
    )
    assert len(docs) == ss._MAX_TYPE_FILES
    assert len(rollup["dropped_files"]) == 3
    assert rollup["dropped_files"] == [
        f"F{i}.swift" for i in range(ss._MAX_TYPE_FILES, ss._MAX_TYPE_FILES + 3)
    ]


def test_build_documents_byte_budget_exhaustion_drops_rest() -> None:
    big = "x" * (ss._WHOLE_FILE_MAX_BYTES)

    def fake_resolve(**_: Any) -> Any:
        # each doc consumes the whole per-file budget; total budget = 400KB
        return _snip(big), None, None

    files = [(f"F{i}.swift", "extension") for i in range(10)]
    docs, rollup = ss.build_documents(
        files,
        project="p",
        repo_path=None,
        commit_sha=None,
        freshness=None,
        resolve=fake_resolve,
    )
    # 400KB / 64KB ≈ 6 full docs, rest dropped (never silent)
    assert rollup["dropped_files"], "budget exhaustion must surface dropped files"
    assert len([d for d in docs if d.source]) < 10
