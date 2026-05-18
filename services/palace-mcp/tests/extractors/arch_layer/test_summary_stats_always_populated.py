"""Tests for arch_layer supplemental query populating module_count (Task 4.3).

Tests verify that _fetch_arch_layer_supplement returns the correct dict keys,
then that fetch_audit_data merges them into summary_stats.

Mock driver pattern: error-path mocking is allowed per test-design rules;
happy-path unit tests are scoped to the pure dict-merge logic.
"""

from __future__ import annotations

import pytest

from palace_mcp.audit.contracts import RunInfo

# These imports are RED until _fetch_arch_layer_supplement is implemented.
from palace_mcp.audit.fetcher import _fetch_arch_layer_supplement  # type: ignore[attr-defined]


class _FakeRecord:
    """Minimal stand-in for a neo4j Record."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key: str) -> object:
        return self._data[key]


class _FakeResult:
    def __init__(self, record: _FakeRecord | None) -> None:
        self._record = record

    async def single(self) -> _FakeRecord | None:
        return self._record


class _FakeSession:
    def __init__(self, record: _FakeRecord | None) -> None:
        self._record = record

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def run(self, query: str, **_kwargs: object) -> _FakeResult:
        return _FakeResult(self._record)


class _FakeDriver:
    def __init__(self, record: _FakeRecord | None) -> None:
        self._record = record

    def session(self) -> _FakeSession:
        return _FakeSession(self._record)


def _run_info(project: str = "test-proj") -> RunInfo:
    return RunInfo(
        run_id="run-arch",
        extractor_name="arch_layer",
        project=project,
        completed_at="2026-05-14T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_no_rules_path_includes_module_count() -> None:
    record = _FakeRecord(
        {
            "module_count": 12,
            "edge_count": 0,
            "rules_declared": False,
            "rule_source": None,
        }
    )
    driver = _FakeDriver(record)

    result = await _fetch_arch_layer_supplement(driver, _run_info())

    assert result["module_count"] == 12
    assert result["rules_declared"] is False


@pytest.mark.asyncio
async def test_with_rules_path_includes_module_count() -> None:
    record = _FakeRecord(
        {
            "module_count": 8,
            "edge_count": 5,
            "rules_declared": True,
            "rule_source": "docs/arch.yaml",
        }
    )
    driver = _FakeDriver(record)

    result = await _fetch_arch_layer_supplement(driver, _run_info())

    assert result["module_count"] == 8
    assert result["rules_declared"] is True


@pytest.mark.asyncio
async def test_empty_project_zero_modules() -> None:
    # OPTIONAL MATCH with no modules → record with zeros
    record = _FakeRecord(
        {
            "module_count": 0,
            "edge_count": 0,
            "rules_declared": False,
            "rule_source": None,
        }
    )
    driver = _FakeDriver(record)

    result = await _fetch_arch_layer_supplement(driver, _run_info())

    assert result["module_count"] == 0
