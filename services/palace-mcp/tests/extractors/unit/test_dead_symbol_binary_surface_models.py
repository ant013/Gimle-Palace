"""Unit tests for dead_symbol_binary_surface Task 1 models and IDs."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.dead_symbol_binary_surface.identifiers import (
    dead_symbol_id_for,
)
from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    BinarySurfaceRecord,
    BinarySurfaceSource,
    CandidateState,
    Confidence,
    DeadSymbolCandidate,
    DeadSymbolEvidenceMode,
    DeadSymbolEvidenceSource,
    DeadSymbolKind,
    DeadSymbolLanguage,
    SkipReason,
    SurfaceKind,
)

_VALID_BINARY_SURFACE = dict(
    id="surface-1",
    group_id="group/acme",
    project="ios-app",
    module_name="DeadSymbolMiniCore",
    language=DeadSymbolLanguage.SWIFT,
    commit_sha="abc123",
    symbol_key="DeadSymbolMiniCore.PublicButUnused",
    surface_kind=SurfaceKind.PUBLIC_API,
    retention_reason="public symbol exported by API surface",
    source=BinarySurfaceSource.PUBLIC_API_SURFACE,
)


def _valid_candidate() -> dict[str, object]:
    group_id = "group/acme"
    project = "ios-app"
    language = DeadSymbolLanguage.SWIFT
    module_name = "DeadSymbolMiniCore"
    symbol_key = "DeadSymbolMiniCore.UnusedHelper"
    commit_sha = "abc123"
    evidence_source = DeadSymbolEvidenceSource.PERIPHERY
    return dict(
        id=dead_symbol_id_for(
            group_id=group_id,
            project=project,
            language=language,
            module_name=module_name,
            symbol_key=symbol_key,
            commit_sha=commit_sha,
            evidence_source=evidence_source,
        ),
        group_id=group_id,
        project=project,
        module_name=module_name,
        language=language,
        commit_sha=commit_sha,
        symbol_key=symbol_key,
        display_name="UnusedHelper",
        kind=DeadSymbolKind.CLASS,
        evidence_source=evidence_source,
        evidence_mode=DeadSymbolEvidenceMode.STATIC,
        confidence=Confidence.HIGH,
        candidate_state=CandidateState.UNUSED_CANDIDATE,
    )


def test_dead_symbol_id_for_returns_128_bit_hex() -> None:
    value = dead_symbol_id_for(
        group_id="group/acme",
        project="ios-app",
        language=DeadSymbolLanguage.SWIFT,
        module_name="DeadSymbolMiniCore",
        symbol_key="DeadSymbolMiniCore.UnusedHelper",
        commit_sha="abc123",
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
    )
    assert re.fullmatch(r"[0-9a-f]{32}", value) is not None


def test_dead_symbol_id_for_is_stable_across_calls() -> None:
    left = dead_symbol_id_for(
        group_id="group/acme",
        project="ios-app",
        language=DeadSymbolLanguage.SWIFT,
        module_name="DeadSymbolMiniCore",
        symbol_key="DeadSymbolMiniCore.UnusedHelper",
        commit_sha="abc123",
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
    )
    right = dead_symbol_id_for(
        group_id="group/acme",
        project="ios-app",
        language=DeadSymbolLanguage.SWIFT,
        module_name="DeadSymbolMiniCore",
        symbol_key="DeadSymbolMiniCore.UnusedHelper",
        commit_sha="abc123",
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
    )
    assert left == right


def test_dead_symbol_id_excludes_schema_version() -> None:
    left = dead_symbol_id_for(
        group_id="group/acme",
        project="ios-app",
        language=DeadSymbolLanguage.SWIFT,
        module_name="DeadSymbolMiniCore",
        symbol_key="DeadSymbolMiniCore.UnusedHelper",
        commit_sha="abc123",
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
    )
    candidate = DeadSymbolCandidate(**_valid_candidate())
    bumped = candidate.model_copy(
        update={"schema_version": candidate.schema_version + 1}
    )
    assert left == candidate.id
    assert candidate.id == bumped.id


def test_parsed_dead_symbol_candidate_valid_minimal() -> None:
    candidate = DeadSymbolCandidate(**_valid_candidate())
    assert candidate.symbol_key == "DeadSymbolMiniCore.UnusedHelper"
    assert candidate.source_file is None
    assert candidate.source_line is None


def test_binary_surface_record_valid_minimal() -> None:
    record = BinarySurfaceRecord(**_VALID_BINARY_SURFACE)
    assert record.surface_kind is SurfaceKind.PUBLIC_API
    assert record.source is BinarySurfaceSource.PUBLIC_API_SURFACE


def test_candidate_rejects_empty_symbol_key_without_file_line_fallback() -> None:
    with pytest.raises(ValidationError):
        DeadSymbolCandidate(**{**_valid_candidate(), "symbol_key": ""})


def test_candidate_rejects_unknown_confidence() -> None:
    with pytest.raises(ValidationError):
        DeadSymbolCandidate(**{**_valid_candidate(), "confidence": "definitely"})


def test_candidate_rejects_unused_candidate_with_skip_reason() -> None:
    with pytest.raises(ValidationError):
        DeadSymbolCandidate(
            **{
                **_valid_candidate(),
                "skip_reason": SkipReason.GENERATED_CODE,
            }
        )


def test_candidate_rejects_skipped_without_skip_reason() -> None:
    with pytest.raises(ValidationError):
        DeadSymbolCandidate(
            **{
                **_valid_candidate(),
                "candidate_state": CandidateState.SKIPPED,
            }
        )


def test_models_are_frozen() -> None:
    candidate = DeadSymbolCandidate(**_valid_candidate())
    record = BinarySurfaceRecord(**_VALID_BINARY_SURFACE)
    with pytest.raises(ValidationError):
        candidate.display_name = "OtherName"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        record.retention_reason = "other"  # type: ignore[misc]
