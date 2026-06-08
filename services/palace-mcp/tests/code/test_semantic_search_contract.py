"""Contract tests for semantic search API types (GIM-839 D0 / B0).

Acceptance:
- SemanticSearchRequest validates scope and parameter precedence.
- effective_scopes() implements spec §7.5 precedence.
- SemanticSearchHit always includes source_scope.
- SymbolSourceMetadata can represent all required fields.
- GIM-837 migration: default scopes exclude dependency/sdk.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.code.semantic_contract import (
    ScoreComponents,
    SemanticSearchHit,
    SemanticSearchRequest,
    SymbolSourceMetadata,
)
from palace_mcp.code.source_scope import SourceScope


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_valid_single_project(self) -> None:
        req = SemanticSearchRequest(
            query="timer scheduler",
            project="uw-ios-app",
        )
        assert req.resolved_projects() == ["uw-ios-app"]

    def test_valid_multi_project(self) -> None:
        req = SemanticSearchRequest(
            query="timer",
            projects=["uw-ios-app", "bitcoin-kit"],
        )
        assert req.resolved_projects() == ["uw-ios-app", "bitcoin-kit"]

    def test_reject_both_project_and_projects(self) -> None:
        with pytest.raises(ValidationError, match="exactly one"):
            SemanticSearchRequest(
                query="timer",
                project="uw-ios-app",
                projects=["bitcoin-kit"],
            )

    def test_reject_neither_project_nor_projects(self) -> None:
        with pytest.raises(ValidationError, match="exactly one"):
            SemanticSearchRequest(query="timer")

    def test_reject_empty_projects(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            SemanticSearchRequest(query="timer", projects=[])

    def test_reject_too_many_projects(self) -> None:
        with pytest.raises(ValidationError, match="at most 10"):
            SemanticSearchRequest(
                query="timer",
                projects=[f"p{i}" for i in range(11)],
            )

    def test_reject_empty_source_scopes(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            SemanticSearchRequest(
                query="timer",
                project="uw-ios-app",
                source_scopes=[],
            )

    def test_reject_empty_query(self) -> None:
        with pytest.raises(ValidationError):
            SemanticSearchRequest(query="", project="uw-ios-app")


# ---------------------------------------------------------------------------
# Effective scope resolution (spec §7.5)
# ---------------------------------------------------------------------------


class TestEffectiveScopes:
    def test_default_scopes_are_first_party(self) -> None:
        req = SemanticSearchRequest(query="timer", project="uw-ios-app")
        scopes = req.effective_scopes()
        assert scopes == frozenset({SourceScope.PROJECT, SourceScope.WORKSPACE_PACKAGE})

    def test_include_dependencies_adds_dependency(self) -> None:
        req = SemanticSearchRequest(
            query="timer",
            project="uw-ios-app",
            include_dependencies=True,
        )
        scopes = req.effective_scopes()
        assert SourceScope.DEPENDENCY in scopes
        assert SourceScope.PROJECT in scopes
        assert SourceScope.WORKSPACE_PACKAGE in scopes

    def test_include_generated_adds_generated_and_derived(self) -> None:
        req = SemanticSearchRequest(
            query="timer",
            project="uw-ios-app",
            include_generated=True,
        )
        scopes = req.effective_scopes()
        assert SourceScope.GENERATED in scopes
        assert SourceScope.DERIVED in scopes

    def test_include_sdk_adds_sdk(self) -> None:
        req = SemanticSearchRequest(
            query="timer",
            project="uw-ios-app",
            include_sdk=True,
        )
        scopes = req.effective_scopes()
        assert SourceScope.SDK in scopes

    def test_explicit_source_scopes_override_flags(self) -> None:
        req = SemanticSearchRequest(
            query="timer",
            project="uw-ios-app",
            source_scopes=[SourceScope.DEPENDENCY, SourceScope.SDK],
            include_dependencies=False,
            include_sdk=False,
        )
        scopes = req.effective_scopes()
        assert scopes == frozenset({SourceScope.DEPENDENCY, SourceScope.SDK})
        assert SourceScope.PROJECT not in scopes

    def test_all_flags_combined(self) -> None:
        req = SemanticSearchRequest(
            query="timer",
            project="uw-ios-app",
            include_dependencies=True,
            include_generated=True,
            include_sdk=True,
        )
        scopes = req.effective_scopes()
        assert scopes == frozenset(SourceScope)


# ---------------------------------------------------------------------------
# GIM-837 migration: default excludes dependency/sdk
# ---------------------------------------------------------------------------


class TestMigrationBehavior:
    def test_default_excludes_dependency(self) -> None:
        req = SemanticSearchRequest(query="hex", project="uw-ios-app")
        assert SourceScope.DEPENDENCY not in req.effective_scopes()

    def test_default_excludes_sdk(self) -> None:
        req = SemanticSearchRequest(query="hex", project="uw-ios-app")
        assert SourceScope.SDK not in req.effective_scopes()

    def test_default_excludes_generated(self) -> None:
        req = SemanticSearchRequest(query="hex", project="uw-ios-app")
        assert SourceScope.GENERATED not in req.effective_scopes()

    def test_default_excludes_derived(self) -> None:
        req = SemanticSearchRequest(query="hex", project="uw-ios-app")
        assert SourceScope.DERIVED not in req.effective_scopes()


# ---------------------------------------------------------------------------
# SemanticSearchHit always has source_scope
# ---------------------------------------------------------------------------


class TestHitContract:
    def test_hit_requires_source_scope(self) -> None:
        hit = SemanticSearchHit(
            project="uw-ios-app",
            group_id="project/uw-ios-app",
            qualified_name="Unstoppable.BalanceService.refreshBalance()",
            file_path="Unstoppable/Services/BalanceService.swift",
            source_scope=SourceScope.PROJECT,
            score=0.85,
            score_components=ScoreComponents(
                vector_score_normalized=0.80,
                lexical_match=0.10,
                source_scope_score=1.0,
            ),
        )
        assert hit.source_scope == SourceScope.PROJECT
        assert hit.score_components.vector_score_normalized == 0.80

    def test_hit_missing_source_scope_fails(self) -> None:
        with pytest.raises(ValidationError):
            SemanticSearchHit(  # type: ignore[call-arg]
                project="uw-ios-app",
                group_id="project/uw-ios-app",
                qualified_name="Unstoppable.Foo",
                score=0.5,
            )

    def test_cross_project_hits_preserve_provenance(self) -> None:
        hit_app = SemanticSearchHit(
            project="uw-ios-app",
            group_id="project/uw-ios-app",
            qualified_name="Unstoppable.HexHelper.toHex()",
            source_scope=SourceScope.PROJECT,
            score=0.9,
        )
        hit_kit = SemanticSearchHit(
            project="hs-toolkit",
            group_id="project/hs-toolkit",
            qualified_name="HsToolKit.HexHelper.toHex()",
            source_scope=SourceScope.PROJECT,
            score=0.88,
        )
        assert hit_app.project != hit_kit.project
        assert hit_app.group_id != hit_kit.group_id


# ---------------------------------------------------------------------------
# SymbolSourceMetadata
# ---------------------------------------------------------------------------


class TestSymbolSourceMetadata:
    def test_full_metadata(self) -> None:
        meta = SymbolSourceMetadata(
            source_scope=SourceScope.PROJECT,
            file_path="Unstoppable/Services/BalanceService.swift",
            line_start=120,
            line_end=148,
            commit_sha="abc123def456",
            project_root="uw-ios-app",
        )
        assert meta.source_scope == SourceScope.PROJECT
        assert meta.line_start == 120

    def test_minimal_metadata(self) -> None:
        meta = SymbolSourceMetadata(
            source_scope=SourceScope.DEPENDENCY,
            file_path="Carthage/Checkouts/Lib/Src.swift",
            project_root="uw-ios-app",
        )
        assert meta.line_start is None
        assert meta.commit_sha is None

    def test_metadata_requires_source_scope(self) -> None:
        with pytest.raises(ValidationError):
            SymbolSourceMetadata(  # type: ignore[call-arg]
                file_path="Sources/Foo.swift",
                project_root="my-project",
            )
