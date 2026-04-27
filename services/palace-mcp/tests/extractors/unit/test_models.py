"""Unit tests for foundation/models.py (GIM-101a, T1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.foundation.models import (
    UNRESOLVED_VERSION_SENTINEL,
    Ecosystem,
    EvictionRecord,
    ExternalDependency,
    IngestCheckpoint,
    Language,
    SourceType,
    SymbolKind,
    SymbolOccurrence,
    SymbolOccurrenceShadow,
)


def _sym_occ(
    symbol_id: int = 42,
    file_path: str = "src/foo.py",
    line: int = 10,
    col_start: int = 4,
    col_end: int = 7,
    **kwargs: object,
) -> SymbolOccurrence:
    defaults = dict(
        doc_key=f"{symbol_id}:{file_path}:{line}:{col_start}",
        symbol_id=symbol_id,
        symbol_qualified_name="foo.bar.Baz",
        kind=SymbolKind.DEF,
        language=Language.PYTHON,
        file_path=file_path,
        line=line,
        col_start=col_start,
        col_end=col_end,
        importance=0.5,
        commit_sha="abc123",
        ingest_run_id="run-1",
    )
    defaults.update(kwargs)  # type: ignore[arg-type]
    return SymbolOccurrence(**defaults)


class TestSymbolKind:
    def test_has_event_and_modifier(self) -> None:
        assert SymbolKind.EVENT == "event"
        assert SymbolKind.MODIFIER == "modifier"

    def test_all_kinds_present(self) -> None:
        kinds = {k.value for k in SymbolKind}
        assert kinds == {"def", "decl", "impl", "use", "assign", "event", "modifier"}


class TestLanguage:
    def test_nine_languages_plus_unknown(self) -> None:
        non_unknown = [l for l in Language if l != Language.UNKNOWN]
        assert len(non_unknown) == 9


class TestSymbolOccurrence:
    def test_valid_occurrence(self) -> None:
        occ = _sym_occ()
        assert occ.symbol_id == 42

    def test_doc_key_mismatch_raises(self) -> None:
        with pytest.raises(ValidationError, match="doc_key"):
            _sym_occ(doc_key="wrong:key")

    def test_col_end_lt_col_start_raises(self) -> None:
        with pytest.raises(ValidationError, match="col_end"):
            _sym_occ(col_start=10, col_end=5)

    def test_col_end_equals_col_start_ok(self) -> None:
        occ = _sym_occ(col_start=5, col_end=5)
        assert occ.col_end == occ.col_start

    def test_symbol_id_min_boundary(self) -> None:
        sid = -(2**63)
        occ = _sym_occ(symbol_id=sid, doc_key=f"{sid}:src/foo.py:10:4")
        assert occ.symbol_id == sid

    def test_symbol_id_max_boundary(self) -> None:
        sid = 2**63 - 1
        occ = _sym_occ(symbol_id=sid, doc_key=f"{sid}:src/foo.py:10:4")
        assert occ.symbol_id == sid

    def test_symbol_id_overflow_raises(self) -> None:
        with pytest.raises(ValidationError):
            _sym_occ(symbol_id=2**63)

    def test_importance_clamp_max(self) -> None:
        with pytest.raises(ValidationError):
            _sym_occ(importance=1.01)

    def test_importance_clamp_min(self) -> None:
        with pytest.raises(ValidationError):
            _sym_occ(importance=-0.01)

    def test_synthesized_by_optional(self) -> None:
        occ = _sym_occ(synthesized_by="synthetic_harness")
        assert occ.synthesized_by == "synthetic_harness"

    def test_schema_version_default(self) -> None:
        occ = _sym_occ()
        assert occ.schema_version == 1

    def test_frozen(self) -> None:
        occ = _sym_occ()
        with pytest.raises(Exception):
            occ.line = 99  # type: ignore[misc]


class TestExternalDependency:
    def test_valid_dep(self) -> None:
        dep = ExternalDependency(
            purl="pkg:pypi/requests@2.31.0",
            ecosystem=Ecosystem.PYPI,
            resolved_version="2.31.0",
            group_id="project/gimle",
        )
        assert dep.resolved_version == "2.31.0"

    def test_unresolved_sentinel_accepted(self) -> None:
        dep = ExternalDependency(
            purl="pkg:npm/lodash",
            ecosystem=Ecosystem.NPM,
            resolved_version=UNRESOLVED_VERSION_SENTINEL,
            group_id="project/gimle",
        )
        assert dep.resolved_version == "unresolved"

    def test_empty_resolved_version_raises(self) -> None:
        with pytest.raises(ValidationError, match="resolved_version"):
            ExternalDependency(
                purl="pkg:pypi/foo",
                ecosystem=Ecosystem.PYPI,
                resolved_version="",
                group_id="project/gimle",
            )


class TestEvictionRecord:
    def test_valid_record(self) -> None:
        rec = EvictionRecord(
            symbol_qualified_name="foo.bar.Baz",
            project="gimle",
            eviction_round="round_1",
            evicted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id="run-abc",
        )
        assert rec.eviction_round == "round_1"

    def test_invalid_round_raises(self) -> None:
        with pytest.raises(ValidationError):
            EvictionRecord(
                symbol_qualified_name="foo",
                project="gimle",
                eviction_round="round_4",  # type: ignore[arg-type]
                evicted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                run_id="run-abc",
            )


class TestIngestCheckpoint:
    def test_valid_checkpoint(self) -> None:
        cp = IngestCheckpoint(
            run_id="run-1",
            project="gimle",
            phase="phase1_defs",
            expected_doc_count=1000,
            completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert cp.expected_doc_count == 1000

    def test_negative_doc_count_raises(self) -> None:
        with pytest.raises(ValidationError):
            IngestCheckpoint(
                run_id="run-1",
                project="gimle",
                phase="phase1_defs",
                expected_doc_count=-1,
                completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )


class TestSourceType:
    def test_has_synthetic(self) -> None:
        assert SourceType.SYNTHETIC == "synthetic"


class TestSymbolOccurrenceShadow:
    def test_valid_shadow(self) -> None:
        shadow = SymbolOccurrenceShadow(
            symbol_id=42,
            symbol_qualified_name="foo.bar.Baz",
            importance=0.7,
            kind=SymbolKind.DEF,
            tier_weight=0.5,
            last_seen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            group_id="project/gimle",
        )
        assert shadow.importance == 0.7
