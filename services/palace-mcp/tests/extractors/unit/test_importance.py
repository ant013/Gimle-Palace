"""Unit tests for BoundedInDegreeCounter and importance_score (GIM-101a, T2 + T4)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from palace_mcp.extractors.foundation.importance import (
    BoundedInDegreeCounter,
    KIND_WEIGHT,
    importance_score,
    recency_decay,
    tier_weight,
)
from palace_mcp.extractors.foundation.models import Language, SymbolKind


# ---------------------------------------------------------------------------
# BoundedInDegreeCounter — T2 acceptance criteria
# ---------------------------------------------------------------------------

class TestBoundedInDegreeCounter:
    def test_increment_and_estimate(self) -> None:
        c = BoundedInDegreeCounter(max_entries=100)
        c.increment("foo.bar")
        c.increment("foo.bar")
        assert c.estimate("foo.bar") == 2

    def test_estimate_missing_returns_zero(self) -> None:
        c = BoundedInDegreeCounter()
        assert c.estimate("nonexistent") == 0

    def test_uniform_load_eviction_removes_exactly_n(self) -> None:
        """F-C acceptance: uniform load → eviction removes EXACTLY max//10 entries."""
        max_entries = 100
        c = BoundedInDegreeCounter(max_entries=max_entries)
        evict_n = max_entries // 10  # 10

        # Insert 1.1× max entries with identical counts (uniform load)
        trigger = max_entries + max_entries // 10 + 1
        for i in range(trigger):
            c.increment(f"sym_{i}")

        # After trigger, eviction fires: removes exactly 10 entries
        # post-eviction count should be trigger - evict_n
        assert len(c) == trigger - evict_n

    def test_eviction_via_batched_trigger(self) -> None:
        """Eviction fires once batch trigger is exceeded, not on every increment."""
        c = BoundedInDegreeCounter(max_entries=50)
        for i in range(50 + 50 // 10 + 1):
            c.increment(f"x_{i}")
        # After one eviction pass (removes 50//10=5):
        assert len(c) < 56  # triggered at 55+1=56, then -5

    def test_to_disk_and_from_disk_roundtrip(self, tmp_path: Path) -> None:
        c = BoundedInDegreeCounter()
        c.increment("a")
        c.increment("a")
        c.increment("b")

        path = tmp_path / "counter.json"
        c.to_disk(path, run_id="run-1")

        c2 = BoundedInDegreeCounter()
        assert c2.from_disk(path, expected_run_id="run-1") is True
        assert c2.estimate("a") == 2
        assert c2.estimate("b") == 1

    def test_from_disk_stale_run_id_returns_false(self, tmp_path: Path) -> None:
        """F-E: stale run_id → return False (caller must hard-fail)."""
        c = BoundedInDegreeCounter()
        c.increment("a")
        path = tmp_path / "counter.json"
        c.to_disk(path, run_id="run-old")

        c2 = BoundedInDegreeCounter()
        assert c2.from_disk(path, expected_run_id="run-new") is False

    def test_from_disk_corrupt_json_returns_false(self, tmp_path: Path) -> None:
        """F-D: corrupt JSON → return False (hard-fail, not silent empty)."""
        path = tmp_path / "counter.json"
        path.write_text("not-json{{{", encoding="utf-8")

        c = BoundedInDegreeCounter()
        assert c.from_disk(path, expected_run_id="any") is False

    def test_from_disk_missing_file_returns_false(self, tmp_path: Path) -> None:
        c = BoundedInDegreeCounter()
        assert c.from_disk(tmp_path / "nonexistent.json", expected_run_id="any") is False

    def test_from_disk_wrong_version_returns_false(self, tmp_path: Path) -> None:
        path = tmp_path / "counter.json"
        path.write_text(
            json.dumps({"version": 99, "run_id": "r1", "counts": {}}),
            encoding="utf-8",
        )
        c = BoundedInDegreeCounter()
        assert c.from_disk(path, expected_run_id="r1") is False

    def test_from_disk_bad_counts_type_returns_false(self, tmp_path: Path) -> None:
        path = tmp_path / "counter.json"
        path.write_text(
            json.dumps({"version": 1, "run_id": "r1", "counts": "bad"}),
            encoding="utf-8",
        )
        c = BoundedInDegreeCounter()
        assert c.from_disk(path, expected_run_id="r1") is False


# ---------------------------------------------------------------------------
# importance_score — T4 acceptance criteria
# ---------------------------------------------------------------------------

class TestTierWeight:
    def test_first_party_path(self) -> None:
        assert tier_weight("src/palace_mcp/models.py") == 1.0

    def test_node_modules(self) -> None:
        assert tier_weight("node_modules/lodash/index.js") == 0.1

    def test_vendor_dir(self) -> None:
        assert tier_weight("vendor/github.com/foo/bar.go") == 0.1

    def test_venv(self) -> None:
        assert tier_weight(".venv/lib/python3.12/site.py") == 0.1

    def test_pycache(self) -> None:
        assert tier_weight("src/__pycache__/foo.pyc") == 0.05

    def test_dist(self) -> None:
        assert tier_weight("dist/bundle.js") == 0.15


class TestImportanceScore:
    _now = datetime.now(tz=timezone.utc)

    def _score(self, **kwargs: object) -> float:
        defaults: dict[str, object] = dict(
            cms_in_degree=10,
            file_path="src/foo.py",
            kind=SymbolKind.DEF,
            last_seen_at=self._now,
            language=Language.PYTHON,
            primary_lang=Language.PYTHON,
        )
        defaults.update(kwargs)
        return importance_score(**defaults)  # type: ignore[arg-type]

    def test_output_in_unit_interval(self) -> None:
        s = self._score()
        assert 0.0 <= s <= 1.0

    def test_high_in_degree_approaches_one(self) -> None:
        s = self._score(cms_in_degree=10_000)
        assert s >= 0.9

    def test_zero_in_degree_nonzero(self) -> None:
        s = self._score(cms_in_degree=0)
        assert s > 0.0  # tier + kind + recency + lang still contribute

    def test_vendor_path_lower_score(self) -> None:
        s1 = self._score(file_path="src/foo.py")
        s2 = self._score(file_path="node_modules/foo/index.js")
        assert s1 > s2

    def test_def_higher_than_use(self) -> None:
        s_def = self._score(kind=SymbolKind.DEF)
        s_use = self._score(kind=SymbolKind.USE)
        assert s_def > s_use

    def test_solidity_event_weight(self) -> None:
        w = KIND_WEIGHT[SymbolKind.EVENT]
        assert w == 0.55

    def test_solidity_modifier_weight(self) -> None:
        w = KIND_WEIGHT[SymbolKind.MODIFIER]
        assert w == 0.6

    def test_old_symbol_lower_recency(self) -> None:
        old = self._now - timedelta(days=180)
        s_new = self._score(last_seen_at=self._now)
        s_old = self._score(last_seen_at=old)
        assert s_new > s_old

    def test_clamp_at_one(self) -> None:
        s = self._score(cms_in_degree=999_999)
        assert s <= 1.0

    def test_clamp_at_zero(self) -> None:
        # Extreme case: unknown language, vendor path, use kind, very old
        old = self._now - timedelta(days=365 * 10)
        s = self._score(
            cms_in_degree=0,
            file_path="node_modules/foo.js",
            kind=SymbolKind.USE,
            last_seen_at=old,
            language=Language.UNKNOWN,
            primary_lang=None,
        )
        assert s >= 0.0


class TestRecencyDecay:
    def test_zero_days_is_one(self) -> None:
        assert recency_decay(0.0) == pytest.approx(1.0)

    def test_half_life_is_half(self) -> None:
        assert recency_decay(30.0, half_life_days=30.0) == pytest.approx(0.5, rel=1e-3)

    def test_long_decay_approaches_zero(self) -> None:
        assert recency_decay(1000.0) < 0.01
