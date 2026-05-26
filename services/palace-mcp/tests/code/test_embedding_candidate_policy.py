"""Tests for embedding_candidate_policy (spec §7.6)."""

from __future__ import annotations

from palace_mcp.code.embedding_candidate_policy import (
    CandidateRow,
    _bucket,
    _is_accessor,
    _is_definition,
    apply_policy,
)


def _row(
    *,
    qualified_name: str = "Pkg.Foo",
    kind: str | None = None,
    file_path: str | None = "src/foo.py",
    source_scope: str | None = "project",
) -> CandidateRow:
    return CandidateRow(
        qualified_name=qualified_name,
        kind=kind,
        file_path=file_path,
        source_scope=source_scope,
    )


# ---------------------------------------------------------------------------
# _is_accessor
# ---------------------------------------------------------------------------


class TestIsAccessor:
    def test_getter_kind(self) -> None:
        assert _is_accessor(_row(kind="getter"))

    def test_setter_kind(self) -> None:
        assert _is_accessor(_row(kind="setter"))

    def test_accessor_kind(self) -> None:
        assert _is_accessor(_row(kind="accessor"))

    def test_dollar_in_name(self) -> None:
        assert _is_accessor(_row(qualified_name="Foo$body"))

    def test_regular_function(self) -> None:
        assert not _is_accessor(_row(kind="function"))

    def test_none_kind(self) -> None:
        assert not _is_accessor(_row(kind=None))


# ---------------------------------------------------------------------------
# _is_definition
# ---------------------------------------------------------------------------


class TestIsDefinition:
    def test_class_kind(self) -> None:
        assert _is_definition(_row(kind="class"))

    def test_struct_kind(self) -> None:
        assert _is_definition(_row(kind="struct"))

    def test_enum_kind(self) -> None:
        assert _is_definition(_row(kind="enum"))

    def test_protocol_kind(self) -> None:
        assert _is_definition(_row(kind="protocol"))

    def test_function_is_not_definition(self) -> None:
        assert not _is_definition(_row(kind="function"))

    def test_method_is_not_definition(self) -> None:
        assert not _is_definition(_row(kind="method"))


# ---------------------------------------------------------------------------
# _bucket
# ---------------------------------------------------------------------------


class TestBucket:
    def test_project_definition_is_bucket_0(self) -> None:
        assert _bucket(_row(source_scope="project", kind="class")) == 0

    def test_workspace_package_definition_is_bucket_1(self) -> None:
        assert _bucket(_row(source_scope="workspace_package", kind="struct")) == 1

    def test_project_function_is_bucket_2(self) -> None:
        assert _bucket(_row(source_scope="project", kind="function")) == 2

    def test_workspace_package_function_is_bucket_3(self) -> None:
        assert _bucket(_row(source_scope="workspace_package", kind="function")) == 3

    def test_dependency_function_is_bucket_4(self) -> None:
        assert _bucket(_row(source_scope="dependency", kind="function")) == 4

    def test_generated_is_bucket_5(self) -> None:
        assert _bucket(_row(source_scope="generated")) == 5

    def test_derived_is_bucket_5(self) -> None:
        assert _bucket(_row(source_scope="derived")) == 5

    def test_sdk_is_bucket_6(self) -> None:
        assert _bucket(_row(source_scope="sdk")) == 6

    def test_project_accessor_is_skipped(self) -> None:
        assert _bucket(_row(source_scope="project", kind="getter")) is None

    def test_workspace_package_accessor_is_skipped(self) -> None:
        assert _bucket(_row(source_scope="workspace_package", kind="setter")) is None

    def test_dependency_accessor_is_skipped(self) -> None:
        assert _bucket(_row(source_scope="dependency", kind="accessor")) is None

    def test_unknown_scope_non_accessor_is_bucket_4(self) -> None:
        assert _bucket(_row(source_scope=None, kind="function")) == 4

    def test_unknown_scope_accessor_is_skipped(self) -> None:
        assert _bucket(_row(source_scope=None, kind="getter")) is None


# ---------------------------------------------------------------------------
# apply_policy
# ---------------------------------------------------------------------------


class TestApplyPolicy:
    def test_no_limit_returns_all_non_accessor(self) -> None:
        rows = [
            _row(qualified_name="Foo.bar", source_scope="project", kind="function"),
            _row(qualified_name="Foo.getter", source_scope="project", kind="getter"),
            _row(qualified_name="Dep.fn", source_scope="dependency", kind="function"),
        ]
        selected, coverage = apply_policy(rows, max_symbols=None)
        names = [r["qualified_name"] for r in selected]
        assert "Foo.bar" in names
        assert "Dep.fn" in names
        assert "Foo.getter" not in names
        assert coverage.bounded is False
        assert coverage.max_symbols is None

    def test_max_symbols_truncates_after_sort(self) -> None:
        rows = [
            _row(qualified_name="Sdk.fn", source_scope="sdk", kind="function"),
            _row(qualified_name="Proj.cls", source_scope="project", kind="class"),
            _row(qualified_name="Proj.fn", source_scope="project", kind="function"),
        ]
        selected, coverage = apply_policy(rows, max_symbols=1)
        # Bucket 0 (project class) is highest priority
        assert len(selected) == 1
        assert selected[0]["qualified_name"] == "Proj.cls"
        assert coverage.bounded is True
        assert coverage.max_symbols == 1
        assert coverage.embedded_symbols == 1
        assert coverage.eligible_symbols == 3

    def test_ordering_within_bucket_by_file_path_then_qualified_name(self) -> None:
        rows = [
            _row(
                qualified_name="Z.fn",
                file_path="b/z.py",
                source_scope="project",
                kind="function",
            ),
            _row(
                qualified_name="A.fn",
                file_path="a/a.py",
                source_scope="project",
                kind="function",
            ),
            _row(
                qualified_name="B.fn",
                file_path="a/b.py",
                source_scope="project",
                kind="function",
            ),
        ]
        selected, _ = apply_policy(rows, max_symbols=None)
        names = [r["qualified_name"] for r in selected]
        assert names == ["A.fn", "B.fn", "Z.fn"]

    def test_project_before_workspace_package_before_dependency(self) -> None:
        rows = [
            _row(qualified_name="Dep.fn", source_scope="dependency", kind="function"),
            _row(
                qualified_name="Wp.fn",
                source_scope="workspace_package",
                kind="function",
            ),
            _row(qualified_name="Proj.fn", source_scope="project", kind="function"),
        ]
        selected, _ = apply_policy(rows, max_symbols=None)
        names = [r["qualified_name"] for r in selected]
        assert names.index("Proj.fn") < names.index("Wp.fn")
        assert names.index("Wp.fn") < names.index("Dep.fn")

    def test_definitions_before_functions_within_same_scope(self) -> None:
        rows = [
            _row(
                qualified_name="Proj.fn",
                source_scope="project",
                kind="function",
                file_path="src/a.py",
            ),
            _row(
                qualified_name="Proj.cls",
                source_scope="project",
                kind="class",
                file_path="src/b.py",
            ),
        ]
        selected, _ = apply_policy(rows, max_symbols=None)
        names = [r["qualified_name"] for r in selected]
        assert names.index("Proj.cls") < names.index("Proj.fn")

    def test_coverage_scope_counts_reflect_selected(self) -> None:
        rows = [
            _row(qualified_name="P.cls", source_scope="project", kind="class"),
            _row(qualified_name="P.fn", source_scope="project", kind="function"),
            _row(qualified_name="W.fn", source_scope="workspace_package", kind="function"),
            _row(
                qualified_name="S.fn",
                source_scope="sdk",
                kind="function",
                file_path="Developer/sdk.h",
            ),
        ]
        selected, coverage = apply_policy(rows, max_symbols=2)
        assert coverage.embedded_symbols == 2
        # Bucket 0 (project class) and bucket 2 (project function) are selected
        assert coverage.source_scope_counts.get("project") == 2
        assert coverage.source_scope_counts.get("workspace_package") is None

    def test_empty_rows_returns_empty_with_zero_coverage(self) -> None:
        selected, coverage = apply_policy([], max_symbols=128)
        assert selected == []
        assert coverage.embedded_symbols == 0
        assert coverage.eligible_symbols == 0
        assert coverage.source_scope_counts == {}

    def test_all_accessors_returns_empty(self) -> None:
        rows = [
            _row(source_scope="project", kind="getter"),
            _row(source_scope="project", kind="setter"),
        ]
        selected, coverage = apply_policy(rows, max_symbols=None)
        assert selected == []
        assert coverage.eligible_symbols == 2

    def test_sdk_symbols_included_in_eligible_count(self) -> None:
        rows = [
            _row(qualified_name="Proj.fn", source_scope="project", kind="function"),
            _row(
                qualified_name="Sdk.fn",
                source_scope="sdk",
                kind="function",
                file_path="Developer/sdk.h",
            ),
        ]
        _, coverage = apply_policy(rows, max_symbols=1)
        # sdk is bucket 6, project is bucket 2 → project selected first
        assert coverage.eligible_symbols == 2
        assert coverage.embedded_symbols == 1
