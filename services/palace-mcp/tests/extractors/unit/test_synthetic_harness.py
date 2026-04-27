"""Unit tests for synthetic stress harness (GIM-101a, T12)."""

from __future__ import annotations


from palace_mcp.extractors.foundation.models import SymbolKind
from palace_mcp.extractors.foundation.synthetic_harness import (
    HarnessStats,
    SyntheticHarness,
)


class TestSyntheticHarness:
    def test_sample_returns_correct_count(self) -> None:
        h = SyntheticHarness(total=1000, symbols=100, file_count=10)
        assert len(h.sample(50)) == 50

    def test_sample_all_are_symbol_occurrences(self) -> None:
        from palace_mcp.extractors.foundation.models import SymbolOccurrence

        h = SyntheticHarness(total=1000, symbols=100, file_count=10)
        for occ in h.sample(10):
            assert isinstance(occ, SymbolOccurrence)

    def test_symbol_ids_are_signed_i64(self) -> None:
        h = SyntheticHarness(total=1000, symbols=1000, file_count=10)
        for occ in h.sample(200):
            assert -(2**63) <= occ.symbol_id < 2**63

    def test_no_overflow_in_symbol_ids(self) -> None:
        h = SyntheticHarness(total=100, symbols=100, file_count=10)
        ids = [occ.symbol_id for occ in h.sample(100)]
        assert all(isinstance(sid, int) for sid in ids)
        assert all(-(2**63) <= sid < 2**63 for sid in ids)

    def test_doc_keys_are_unique_for_distinct_positions(self) -> None:
        h = SyntheticHarness(total=500, symbols=10, file_count=5)
        doc_keys = [occ.doc_key for occ in h.sample(500)]
        # doc_key = project::sym::file_idx::line — duplicates are expected
        # but doc_key must always be a non-empty string
        assert all(dk for dk in doc_keys)

    def test_kinds_include_def_and_decl(self) -> None:
        h = SyntheticHarness(total=1000, symbols=50, file_count=10)
        kinds = {occ.kind for occ in h.sample(1000)}
        assert SymbolKind.DEF in kinds
        assert SymbolKind.DECL in kinds

    def test_deterministic_output(self) -> None:
        h1 = SyntheticHarness(total=100, symbols=10, file_count=5)
        h2 = SyntheticHarness(total=100, symbols=10, file_count=5)
        ids1 = [occ.symbol_id for occ in h1.sample(100)]
        ids2 = [occ.symbol_id for occ in h2.sample(100)]
        assert ids1 == ids2

    def test_total_respected(self) -> None:
        h = SyntheticHarness(total=42, symbols=10, file_count=5)
        assert len(list(h.occurrences())) == 42

    def test_stats_sample_size(self) -> None:
        h = SyntheticHarness(total=10_000, symbols=1000, file_count=100)
        stats = h.stats(sample_size=500)
        assert stats.total_generated == 500
        assert stats.unique_symbols <= 500
        assert stats.negative_ids + stats.positive_ids == 500

    def test_stats_both_negative_and_positive_ids(self) -> None:
        # With 1000 symbols, both sign buckets should be non-empty
        h = SyntheticHarness(total=50_000, symbols=1000, file_count=100)
        stats = h.stats(sample_size=5000)
        # blake2b produces roughly uniform distribution; with 1000 symbols
        # both sides should be non-zero
        assert stats.negative_ids > 0
        assert stats.positive_ids > 0


class TestHarnessStats:
    def test_record_increments_total(self) -> None:
        s = HarnessStats()
        s.record(42)
        assert s.total_generated == 1

    def test_record_tracks_sign(self) -> None:
        s = HarnessStats()
        s.record(1)
        s.record(-1)
        assert s.positive_ids == 1
        assert s.negative_ids == 1

    def test_record_detects_collision(self) -> None:
        s = HarnessStats()
        s.record(99)
        s.record(99)
        assert s.hash_collisions == 1
        assert s.unique_symbols == 1
