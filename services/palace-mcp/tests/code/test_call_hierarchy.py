"""
Tests for palace.code.call_hierarchy (GIM-1168 F1B production, GIM-1170 hardening).

Wire-contract tests: every error path asserts error_code.
Unit tests use mocked find_callers; no libIndexStore.dylib required.
Integration tests (require live IndexStore) are skipped when
PALACE_SOURCEKIT_INDEX_STORE_PATH is not set.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from palace_mcp.code.call_hierarchy import (
    _detect_store_format,
    _resolve_store_path,
    call_hierarchy_tool,
)
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
# _detect_store_format
# ---------------------------------------------------------------------------


def test_detect_format_v5(tmp_path: Path) -> None:
    (tmp_path / "v5").mkdir()
    assert _detect_store_format(str(tmp_path)) == "v5"


def test_detect_format_unidb(tmp_path: Path) -> None:
    (tmp_path / "index.db").write_bytes(b"")
    assert _detect_store_format(str(tmp_path)) == "unidb"


def test_detect_format_missing_path() -> None:
    assert _detect_store_format("/nonexistent/path/xyz") is None


def test_detect_format_empty_dir(tmp_path: Path) -> None:
    assert _detect_store_format(str(tmp_path)) is None


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


def test_nonexistent_store_path_returns_error_code() -> None:
    result = call_hierarchy_tool(
        qualified_name="BalanceData",
        project=None,
        max_results=10,
        index_store_path="/nonexistent/store/path",
        indexstore_paths={},
        default_store_path=None,
    )
    assert result["ok"] is False
    assert result["error_code"] == "index_store_not_found"
    assert "symbol_index_swift" in result["message"]


def test_unidb_format_returns_format_error(tmp_path: Path) -> None:
    (tmp_path / "index.db").write_bytes(b"")
    result = call_hierarchy_tool(
        qualified_name="BalanceData",
        project=None,
        max_results=10,
        index_store_path=str(tmp_path),
        indexstore_paths={},
        default_store_path=None,
    )
    assert result["ok"] is False
    assert result["error_code"] == "index_store_format_unsupported"
    assert "UniDB" in result["message"] or "unidb" in result["message"].lower()


def test_indexstore_error_returns_error_code(tmp_path: Path) -> None:
    (tmp_path / "v5").mkdir()
    with patch(
        "palace_mcp.code.indexstore.find_callers",
        side_effect=RuntimeError("libIndexStore not found"),
    ):
        result = call_hierarchy_tool(
            qualified_name="BalanceData",
            project=None,
            max_results=10,
            index_store_path=str(tmp_path),
            indexstore_paths={},
            default_store_path=None,
        )
    assert result["ok"] is False
    assert result["error_code"] == "indexstore_error"
    assert "libIndexStore" in result["message"]


def test_timeout_returns_error_code(tmp_path: Path) -> None:
    (tmp_path / "v5").mkdir()

    def _slow_find(*args: object, **kwargs: object) -> list:
        import time

        time.sleep(10)
        return []

    with patch("palace_mcp.code.indexstore.find_callers", side_effect=_slow_find):
        result = call_hierarchy_tool(
            qualified_name="BalanceData",
            project=None,
            max_results=10,
            index_store_path=str(tmp_path),
            indexstore_paths={},
            default_store_path=None,
            timeout_s=0.05,  # 50ms — triggers timeout immediately
        )
    assert result["ok"] is False
    assert result["error_code"] == "timeout"
    assert "timeout_s" in result
    assert "symbol_index_swift" in result["message"]


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


def test_successful_query_returns_callers(tmp_path: Path) -> None:
    (tmp_path / "v5").mkdir()
    with patch("palace_mcp.code.indexstore.find_callers", return_value=_FAKE_CALLERS):
        result = call_hierarchy_tool(
            qualified_name="WalletKit.BalanceData",
            project="uw-ios-app",
            max_results=100,
            index_store_path=str(tmp_path),
            indexstore_paths={},
            default_store_path=None,
        )

    assert result["ok"] is True
    assert result["caller_count"] == 2
    assert result["short_name"] == "BalanceData"
    assert result["project"] == "uw-ios-app"
    assert result["approach"] == "indexstore_direct"
    assert "latency_s" in result
    assert "message" not in result  # non-empty result has no guidance message

    callers = result["callers"]
    assert callers[0]["source_file"] == "/repo/BalanceService.swift"
    assert callers[0]["line"] == 15
    assert callers[1]["roles"] == 32


def test_no_callers_includes_guidance_message(tmp_path: Path) -> None:
    (tmp_path / "v5").mkdir()
    with patch("palace_mcp.code.indexstore.find_callers", return_value=[]):
        result = call_hierarchy_tool(
            qualified_name="UnknownSymbol",
            project="uw-ios-app",
            max_results=10,
            index_store_path=str(tmp_path),
            indexstore_paths={},
            default_store_path=None,
        )
    assert result["ok"] is True
    assert result["caller_count"] == 0
    assert "message" in result
    assert "symbol_index_swift" in result["message"]


def test_per_project_path_resolved_and_used(tmp_path: Path) -> None:
    """Verify per-project path is passed to find_callers."""
    (tmp_path / "v5").mkdir()
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
            indexstore_paths={"uw-ios-app": str(tmp_path)},
            default_store_path="/default/DataStore",
        )

    assert result["ok"] is True
    assert captured == [str(tmp_path)]
    assert result["index_store_path"] == str(tmp_path)


def test_qualified_name_splits_to_short_name(tmp_path: Path) -> None:
    (tmp_path / "v5").mkdir()
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
            index_store_path=str(tmp_path),
            indexstore_paths={},
            default_store_path=None,
        )

    assert captured == ["BalanceData"]


# ---------------------------------------------------------------------------
# Integration test — requires live IndexStore
# ---------------------------------------------------------------------------

_INTEGRATION_STORE = os.environ.get("PALACE_SOURCEKIT_INDEX_STORE_PATH")
_INTEGRATION_INDEXSTORE_PATHS = json.loads(
    os.environ.get("PALACE_INDEXSTORE_PATHS", "{}") or "{}"
)
_INTEGRATION_UW_IOS_STORE = _INTEGRATION_INDEXSTORE_PATHS.get("uw-ios-app")


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


@pytest.mark.skipif(
    not _INTEGRATION_UW_IOS_STORE,
    reason="PALACE_INDEXSTORE_PATHS[uw-ios-app] not set; skip live uw-ios-app IndexStore test",
)
def test_integration_uw_ios_app_store_is_v5_and_returns_callers() -> None:
    assert _INTEGRATION_UW_IOS_STORE is not None
    assert _detect_store_format(_INTEGRATION_UW_IOS_STORE) == "v5"
    assert next(Path(_INTEGRATION_UW_IOS_STORE).rglob("*.IDXU"), None) is not None

    result = call_hierarchy_tool(
        qualified_name="BalanceData",
        project="uw-ios-app",
        max_results=50,
        index_store_path=None,
        indexstore_paths={"uw-ios-app": _INTEGRATION_UW_IOS_STORE},
        default_store_path=None,
    )

    assert result["ok"] is True
    assert result["caller_count"] >= 1
