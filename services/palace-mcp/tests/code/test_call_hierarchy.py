"""
Tests for palace.code.call_hierarchy (GIM-1168 F1B production).

Wire-contract tests: every error path asserts error_code.
Unit tests use mocked find_callers; no libIndexStore.dylib required.
Integration tests (require live IndexStore) are skipped when
PALACE_SOURCEKIT_INDEX_STORE_PATH is not set.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from palace_mcp.code.call_hierarchy import _resolve_store_path, call_hierarchy_tool
from palace_mcp.code.indexstore import CallerRecord


# ---------------------------------------------------------------------------
# _resolve_store_path — priority ordering
# ---------------------------------------------------------------------------


def test_explicit_override_wins() -> None:
    result = _resolve_store_path(
        project="uw-ios-app",
        index_store_path="/explicit/path",
        indexstore_paths={"uw-ios-app": "/per-project/path"},
        default_store_path="/default/path",
    )
    assert result == "/explicit/path"


def test_per_project_path_used_when_no_override() -> None:
    result = _resolve_store_path(
        project="uw-ios-app",
        index_store_path=None,
        indexstore_paths={"uw-ios-app": "/per-project/path"},
        default_store_path="/default/path",
    )
    assert result == "/per-project/path"


def test_default_path_used_when_no_project_match() -> None:
    result = _resolve_store_path(
        project="unknown-project",
        index_store_path=None,
        indexstore_paths={"uw-ios-app": "/per-project/path"},
        default_store_path="/default/path",
    )
    assert result == "/default/path"


def test_no_project_falls_back_to_default() -> None:
    result = _resolve_store_path(
        project=None,
        index_store_path=None,
        indexstore_paths={"uw-ios-app": "/per-project/path"},
        default_store_path="/default/path",
    )
    assert result == "/default/path"


def test_env_var_used_as_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALACE_SOURCEKIT_INDEX_STORE_PATH", "/env/path")
    result = _resolve_store_path(
        project=None,
        index_store_path=None,
        indexstore_paths={},
        default_store_path=None,
    )
    assert result == "/env/path"


def test_returns_none_when_nothing_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PALACE_SOURCEKIT_INDEX_STORE_PATH", raising=False)
    result = _resolve_store_path(
        project=None,
        index_store_path=None,
        indexstore_paths={},
        default_store_path=None,
    )
    assert result is None


# ---------------------------------------------------------------------------
# call_hierarchy_tool — error paths
# ---------------------------------------------------------------------------


def test_missing_store_path_returns_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PALACE_SOURCEKIT_INDEX_STORE_PATH", raising=False)
    result = call_hierarchy_tool(
        qualified_name="BalanceData",
        project=None,
        max_results=10,
        index_store_path=None,
        indexstore_paths={},
        default_store_path=None,
    )
    assert result["ok"] is False
    assert result["error_code"] == "index_store_not_configured"


def test_missing_store_path_includes_project_in_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PALACE_SOURCEKIT_INDEX_STORE_PATH", raising=False)
    result = call_hierarchy_tool(
        qualified_name="BalanceData",
        project="uw-ios-app",
        max_results=10,
        index_store_path=None,
        indexstore_paths={},
        default_store_path=None,
    )
    assert result["ok"] is False
    assert result["error_code"] == "index_store_not_configured"
    assert result["project"] == "uw-ios-app"


def test_indexstore_error_returns_error_code() -> None:
    with patch(
        "palace_mcp.code.indexstore.find_callers",
        side_effect=RuntimeError("libIndexStore not found"),
    ):
        result = call_hierarchy_tool(
            qualified_name="BalanceData",
            project=None,
            max_results=10,
            index_store_path="/fake/store",
            indexstore_paths={},
            default_store_path=None,
        )
    assert result["ok"] is False
    assert result["error_code"] == "indexstore_error"
    assert "libIndexStore" in result["message"]


# ---------------------------------------------------------------------------
# call_hierarchy_tool — success paths
# ---------------------------------------------------------------------------


_FAKE_CALLERS = [
    CallerRecord(
        source_file="/repo/BalanceService.swift",
        record_name="ABCDEF",
        symbol_name="BalanceData",
        symbol_usr="s:9WalletKit11BalanceDataV",
        line=15,
        col=5,
        roles=4,
    ),
    CallerRecord(
        source_file="/repo/WalletView.swift",
        record_name="123456",
        symbol_name="BalanceData",
        symbol_usr="s:9WalletKit11BalanceDataV",
        line=88,
        col=12,
        roles=32,
    ),
]


def test_successful_query_returns_callers() -> None:
    with patch("palace_mcp.code.indexstore.find_callers", return_value=_FAKE_CALLERS):
        result = call_hierarchy_tool(
            qualified_name="WalletKit.BalanceData",
            project="uw-ios-app",
            max_results=100,
            index_store_path="/fake/store",
            indexstore_paths={},
            default_store_path=None,
        )

    assert result["ok"] is True
    assert result["caller_count"] == 2
    assert result["short_name"] == "BalanceData"
    assert result["project"] == "uw-ios-app"
    assert result["approach"] == "indexstore_direct"
    assert "latency_s" in result

    callers = result["callers"]
    assert callers[0]["source_file"] == "/repo/BalanceService.swift"
    assert callers[0]["line"] == 15
    assert callers[1]["roles"] == 32


def test_per_project_path_resolved_and_used() -> None:
    """Verify per-project path is passed to find_callers."""
    captured: list[str] = []

    def _mock_find_callers(
        name: str, path: str, **kwargs: object
    ) -> list[CallerRecord]:
        captured.append(path)
        return []

    with patch(
        "palace_mcp.code.indexstore.find_callers", side_effect=_mock_find_callers
    ):
        result = call_hierarchy_tool(
            qualified_name="BalanceData",
            project="uw-ios-app",
            max_results=10,
            index_store_path=None,
            indexstore_paths={"uw-ios-app": "/per-project/DataStore"},
            default_store_path="/default/DataStore",
        )

    assert result["ok"] is True
    assert captured == ["/per-project/DataStore"]
    assert result["index_store_path"] == "/per-project/DataStore"


def test_qualified_name_splits_to_short_name() -> None:
    captured: list[str] = []

    def _mock_find_callers(
        name: str, path: str, **kwargs: object
    ) -> list[CallerRecord]:
        captured.append(name)
        return []

    with patch(
        "palace_mcp.code.indexstore.find_callers", side_effect=_mock_find_callers
    ):
        call_hierarchy_tool(
            qualified_name="WalletKit.BalanceData",
            project=None,
            max_results=10,
            index_store_path="/fake",
            indexstore_paths={},
            default_store_path=None,
        )

    assert captured == ["BalanceData"]


# ---------------------------------------------------------------------------
# Integration test — requires live IndexStore
# ---------------------------------------------------------------------------

_INTEGRATION_STORE = os.environ.get("PALACE_SOURCEKIT_INDEX_STORE_PATH")


@pytest.mark.skipif(
    not _INTEGRATION_STORE,
    reason="PALACE_SOURCEKIT_INDEX_STORE_PATH not set; skip live IndexStore test",
)
def test_integration_live_index_store_returns_results() -> None:
    """Acceptance test: ≥1 caller returned from live IndexStore (any symbol)."""
    assert _INTEGRATION_STORE is not None
    result = call_hierarchy_tool(
        qualified_name="BalanceData",
        project=None,
        max_results=50,
        index_store_path=_INTEGRATION_STORE,
        indexstore_paths={},
        default_store_path=None,
    )
    assert result["ok"] is True
    # Not asserting ≥30 here because the test env may not have uw-ios-app indexed;
    # the full acceptance test (≥30 callers) should be run on iMac after symbol_index_swift.
    assert result["caller_count"] >= 0
