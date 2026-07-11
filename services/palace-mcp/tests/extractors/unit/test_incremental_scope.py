from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.foundation.baseline import build_valid_extractor_baseline
from palace_mcp.extractors.foundation.incremental_scope import (
    AUDIT_EXTRACTOR_SCOPE_KINDS,
    AuditScopeKind,
    FILE_SCOPED_AUDIT_EXTRACTORS,
    IncrementalMode,
    _READ_FILE_COMMITS_CYPHER,
    _GitChangeSet,
    derive_swift_delta_scope,
)
from palace_mcp.git.command import GitError


def _settings() -> SimpleNamespace:
    return SimpleNamespace(palace_incremental_ingest=True)


def _baseline():
    return build_valid_extractor_baseline(
        project_id="project/uw-ios-mini",
        project_slug="uw-ios-mini",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
        state_version=1,
        commit_sha="base-sha",
        run_id="baseline-run",
    )


async def _derive(tmp_path: Path, **kwargs):
    return await derive_swift_delta_scope(
        MagicMock(),
        repo_path=tmp_path,
        project_id="project/uw-ios-mini",
        settings=_settings(),
        **kwargs,
    )


def test_audit_scope_inventory_matches_phase2_contract() -> None:
    assert AUDIT_EXTRACTOR_SCOPE_KINDS == {
        "code_ownership": AuditScopeKind.FILE,
        "crypto_domain_model": AuditScopeKind.FILE,
        "error_handling_policy": AuditScopeKind.FILE,
        "coding_convention": AuditScopeKind.MODULE,
        "testability_di": AuditScopeKind.MODULE,
        "localization_accessibility": AuditScopeKind.MIXED,
        "dead_symbol_binary_surface": AuditScopeKind.PROJECT,
    }


def test_file_scoped_audit_extractors_are_only_true_file_local_writers() -> None:
    assert FILE_SCOPED_AUDIT_EXTRACTORS == frozenset(
        {
            "code_ownership",
            "crypto_domain_model",
            "error_handling_policy",
        }
    )


def test_read_existing_commit_sha_coalesces_last_seen_in_commit() -> None:
    assert "last_seen_in_commit" in _READ_FILE_COMMITS_CYPHER
    assert "coalesce(f.last_seen_in_commit, f.commit_sha)" in _READ_FILE_COMMITS_CYPHER


@pytest.mark.asyncio
async def test_swift_delta_scope_reports_missing_baseline(tmp_path: Path) -> None:
    with patch(
        "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
        new=AsyncMock(return_value=None),
    ):
        scope = await _derive(tmp_path)

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "baseline_missing"
    assert scope.baseline_state == "missing"


@pytest.mark.asyncio
async def test_swift_delta_scope_rejects_invalid_baseline(tmp_path: Path) -> None:
    invalid = replace(
        _baseline(),
        status="invalid",
        invalid_reason="baseline_invalidated_by_schema",
    )
    with patch(
        "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
        new=AsyncMock(return_value=invalid),
    ):
        scope = await _derive(tmp_path)

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "baseline_invalidated_by_schema"
    assert scope.baseline_state == "invalid"


@pytest.mark.asyncio
async def test_swift_delta_scope_rejects_schema_mismatch(tmp_path: Path) -> None:
    with patch(
        "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
        new=AsyncMock(return_value=replace(_baseline(), state_version=999)),
    ):
        scope = await _derive(tmp_path)

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "baseline_schema_mismatch"
    assert scope.baseline_state == "invalid"


@pytest.mark.asyncio
async def test_swift_delta_scope_falls_back_on_high_changed_ratio(
    tmp_path: Path,
) -> None:
    with patch(
        "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
        new=AsyncMock(return_value=_baseline()),
    ):
        scope = await _derive(tmp_path, changed_ratio=0.8)

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "high_changed_ratio"
    assert scope.baseline_state == "present"


@pytest.mark.asyncio
async def test_swift_delta_scope_falls_back_on_git_error(tmp_path: Path) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(side_effect=GitError(1, "git diff failed")),
        ),
    ):
        scope = await _derive(tmp_path)

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "git_diff_error"


@pytest.mark.asyncio
async def test_swift_delta_scope_falls_back_on_truncated_git_diff(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(
                return_value=_GitChangeSet(
                    changed={"Sources/App/A.swift"},
                    added=set(),
                    removed=set(),
                    truncated=True,
                )
            ),
        ),
    ):
        scope = await _derive(tmp_path)

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "git_diff_truncated"


@pytest.mark.asyncio
async def test_swift_delta_scope_derives_baseline_only_scope(tmp_path: Path) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(
                return_value=_GitChangeSet(
                    changed={"Sources/App/A.swift", "README.md"},
                    added=set(),
                    removed={"Sources/App/Old.swift"},
                    truncated=False,
                )
            ),
        ),
    ):
        scope = await _derive(tmp_path)

    assert scope.mode == IncrementalMode.INCREMENTAL
    assert scope.changed_paths == {"Sources/App/A.swift"}
    assert scope.removed_paths == {"Sources/App/Old.swift"}
    assert scope.validated_by == "baseline_only"


@pytest.mark.asyncio
async def test_swift_delta_scope_derives_symbol_validated_scope(tmp_path: Path) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(
                return_value=_GitChangeSet(
                    changed={"Sources/App/A.swift"},
                    added=set(),
                    removed=set(),
                    truncated=False,
                )
            ),
        ),
    ):
        scope = await _derive(
            tmp_path,
            scip_paths={"Sources/App/A.swift"},
            body_changed_paths={"Sources/App/A.swift"},
            body_removed_paths=set(),
        )

    assert scope.mode == IncrementalMode.INCREMENTAL
    assert scope.changed_paths == {"Sources/App/A.swift"}
    assert scope.validated_by == "symbol_index_swift"


@pytest.mark.asyncio
async def test_swift_delta_scope_falls_back_on_scip_path_mismatch(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(
                return_value=_GitChangeSet(
                    changed={"Sources/App/A.swift"},
                    added=set(),
                    removed=set(),
                    truncated=False,
                )
            ),
        ),
    ):
        scope = await _derive(tmp_path, scip_paths=set())

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "scip_path_mismatch"


@pytest.mark.asyncio
async def test_swift_delta_scope_falls_back_on_body_hash_change_mismatch(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(
                return_value=_GitChangeSet(
                    changed={"Sources/App/A.swift"},
                    added=set(),
                    removed=set(),
                    truncated=False,
                )
            ),
        ),
    ):
        scope = await _derive(
            tmp_path,
            scip_paths={"Sources/App/A.swift"},
            body_changed_paths=set(),
        )

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "body_hash_changed_mismatch"


@pytest.mark.asyncio
async def test_swift_delta_scope_falls_back_on_body_hash_removal_mismatch(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "palace_mcp.extractors.foundation.incremental_scope.load_extractor_baseline",
            new=AsyncMock(return_value=_baseline()),
        ),
        patch(
            "palace_mcp.extractors.foundation.incremental_scope._read_git_change_set",
            new=AsyncMock(
                return_value=_GitChangeSet(
                    changed=set(),
                    added=set(),
                    removed={"Sources/App/Old.swift"},
                    truncated=False,
                )
            ),
        ),
    ):
        scope = await _derive(
            tmp_path,
            scip_paths=set(),
            body_removed_paths=set(),
        )

    assert scope.mode == IncrementalMode.FULL
    assert scope.reason == "body_hash_removed_mismatch"
