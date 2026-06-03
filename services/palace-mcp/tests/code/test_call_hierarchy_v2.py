"""
Tests for palace.code.call_hierarchy_v2 (GIM-1167 F1B-SPIKE-V2).

Wire-contract tests: every error path asserts the error_code field.
Unit tests use a mock IndexStore so libIndexStore.dylib is not required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.code.call_hierarchy_v2 import call_hierarchy_v2_tool
from palace_mcp.code.indexstore import CallerRecord


# ---------------------------------------------------------------------------
# call_hierarchy_v2_tool — error paths
# ---------------------------------------------------------------------------


def test_missing_store_path_returns_error_code() -> None:
    result = call_hierarchy_v2_tool(
        qualified_name="BalanceData",
        project=None,
        max_results=10,
        index_store_path=None,
    )
    assert result["ok"] is False
    assert result["error_code"] == "index_store_not_configured"


def test_indexstore_exception_returns_error_code() -> None:
    with patch(
        "palace_mcp.code.indexstore.find_callers",
        side_effect=RuntimeError("libIndexStore not found"),
    ):
        result = call_hierarchy_v2_tool(
            qualified_name="BalanceData",
            project=None,
            max_results=10,
            index_store_path="/fake/store",
        )
    assert result["ok"] is False
    assert result["error_code"] == "indexstore_error"
    assert "libIndexStore" in result["message"]


def test_successful_query_returns_callers() -> None:
    fake_callers = [
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
            roles=32,  # CALL
        ),
    ]
    with patch("palace_mcp.code.indexstore.find_callers", return_value=fake_callers):
        result = call_hierarchy_v2_tool(
            qualified_name="WalletKit.BalanceData",
            project="uw-ios-app",
            max_results=100,
            index_store_path="/fake/store",
        )

    assert result["ok"] is True
    assert result["caller_count"] == 2
    assert result["short_name"] == "BalanceData"
    assert result["approach"] == "indexstore_direct"
    assert "latency_s" in result

    callers = result["callers"]
    assert callers[0]["source_file"] == "/repo/BalanceService.swift"
    assert callers[0]["line"] == 15
    assert callers[1]["roles"] == 32


def test_qualified_name_splits_to_short_name() -> None:
    """short_name extraction: 'WalletKit.BalanceData' → 'BalanceData'."""
    captured: list[str] = []

    def _mock_find_callers(name: str, path: str, **kwargs: object) -> list[CallerRecord]:
        captured.append(name)
        return []

    with patch("palace_mcp.code.indexstore.find_callers", side_effect=_mock_find_callers):
        call_hierarchy_v2_tool(
            qualified_name="WalletKit.BalanceData",
            project=None,
            max_results=10,
            index_store_path="/fake",
        )

    assert captured == ["BalanceData"]


# ---------------------------------------------------------------------------
# find_callers — error paths (mocked _BoundLib)
# ---------------------------------------------------------------------------


def test_find_callers_raises_on_bad_store_path() -> None:
    from palace_mcp.code import indexstore as _is

    mock_lib = MagicMock()
    mock_lib.indexstore_store_create.return_value = None  # simulate failure

    with patch.object(_is, "_bound", mock_lib):
        with pytest.raises(RuntimeError, match="indexstore_store_create failed"):
            _is.find_callers("BalanceData", "/nonexistent/store")
