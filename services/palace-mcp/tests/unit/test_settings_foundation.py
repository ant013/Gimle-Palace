"""Unit tests for Settings extractor-foundation extensions (GIM-101a, T9)."""

from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from palace_mcp.config import Settings


def _minimal_env() -> dict[str, str]:
    """Env with required secrets filled in."""
    return {
        "NEO4J_PASSWORD": "test-secret",
        "OPENAI_API_KEY": "sk-test",
    }


class TestSettingsFoundationDefaults:
    def test_max_occurrences_total_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_max_occurrences_total == 50_000_000

    def test_max_occurrences_per_project_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_max_occurrences_per_project == 10_000_000

    def test_importance_threshold_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_importance_threshold_use == 0.05

    def test_max_per_symbol_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_max_occurrences_per_symbol == 5_000

    def test_recency_decay_days_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_recency_decay_days == 30.0

    def test_tantivy_index_path_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_tantivy_index_path == "/var/lib/palace/tantivy"

    def test_tantivy_heap_mb_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_tantivy_heap_mb == 100

    def test_scip_index_paths_default_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.palace_scip_index_paths == {}


class TestSettingsFoundationOverrides:
    def test_scip_index_paths_json_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        payload = json.dumps({"gimle": "/repos/gimle/.scip/index.scip"})
        monkeypatch.setenv("PALACE_SCIP_INDEX_PATHS", payload)
        s = Settings()
        assert s.palace_scip_index_paths == {"gimle": "/repos/gimle/.scip/index.scip"}

    def test_tantivy_heap_mb_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("PALACE_TANTIVY_HEAP_MB", "256")
        s = Settings()
        assert s.palace_tantivy_heap_mb == 256

    def test_max_occurrences_total_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("PALACE_MAX_OCCURRENCES_TOTAL", "70000000")
        s = Settings()
        assert s.palace_max_occurrences_total == 70_000_000

    def test_importance_threshold_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _minimal_env().items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("PALACE_IMPORTANCE_THRESHOLD_USE", "1.1")
        with pytest.raises(ValidationError):
            Settings()
