"""Unit tests for S0 anchor symbols (GIM-1097).

Covers:
- make_symbol() is_anchor field propagation
- Settings.palace_anchor_symbols JSON parsing
- get_anchor_qnames() config look-up helper
"""

from __future__ import annotations

import json

import pytest

from palace_mcp.graphiti_schema.entities import make_symbol
from palace_mcp.memory.projects import get_anchor_qnames


# ---------------------------------------------------------------------------
# make_symbol() anchor field
# ---------------------------------------------------------------------------


def _sym(**kwargs: object) -> object:
    defaults = dict(
        group_id="project/uw-ios-app",
        name="BalanceData",
        kind="class",
        extractor="test",
        extractor_version="0.0.1",
    )
    return make_symbol(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_make_symbol_is_anchor_default_false() -> None:
    node = _sym()
    assert node.attributes["is_anchor"] is False


def test_make_symbol_is_anchor_true() -> None:
    node = _sym(is_anchor=True)
    assert node.attributes["is_anchor"] is True


def test_make_symbol_anchor_and_extra_coexist() -> None:
    # extra dict should not silently shadow is_anchor kwarg
    node = _sym(is_anchor=True, extra={"qualified_name": "WalletKit.BalanceData"})
    assert node.attributes["is_anchor"] is True
    assert node.attributes["qualified_name"] == "WalletKit.BalanceData"


# ---------------------------------------------------------------------------
# Settings.palace_anchor_symbols JSON parsing
# ---------------------------------------------------------------------------


def test_settings_anchor_symbols_empty_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PALACE_ANCHOR_SYMBOLS", raising=False)
    from palace_mcp.config import Settings

    s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
    assert s.palace_anchor_symbols == {}


def test_settings_anchor_symbols_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {"project/uw-ios-app": ["WalletKit.BalanceData", "WalletKit.Transaction"]}
    )
    monkeypatch.setenv("PALACE_ANCHOR_SYMBOLS", payload)
    from importlib import reload
    import palace_mcp.config as cfg_module

    reload(cfg_module)
    s = cfg_module.Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
    assert s.palace_anchor_symbols == {
        "project/uw-ios-app": ["WalletKit.BalanceData", "WalletKit.Transaction"]
    }


def test_settings_anchor_symbols_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALACE_ANCHOR_SYMBOLS", "")
    from palace_mcp.config import Settings

    s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
    assert s.palace_anchor_symbols == {}


# ---------------------------------------------------------------------------
# get_anchor_qnames()
# ---------------------------------------------------------------------------


class _FakeSettings:
    palace_anchor_symbols: dict[str, list[str]]

    def __init__(self, anchors: dict[str, list[str]]) -> None:
        self.palace_anchor_symbols = anchors


def test_get_anchor_qnames_single_group() -> None:
    settings = _FakeSettings({"project/uw-ios-app": ["A.B", "A.C"]})  # type: ignore[arg-type]
    result = get_anchor_qnames(["project/uw-ios-app"], settings)  # type: ignore[arg-type]
    assert result == ["A.B", "A.C"]


def test_get_anchor_qnames_multi_group() -> None:
    settings = _FakeSettings(  # type: ignore[arg-type]
        {
            "project/uw-ios-app": ["A.B"],
            "project/gimle": ["Foo.Bar"],
        }
    )
    result = get_anchor_qnames(["project/uw-ios-app", "project/gimle"], settings)  # type: ignore[arg-type]
    assert result == ["A.B", "Foo.Bar"]


def test_get_anchor_qnames_unknown_group_returns_empty() -> None:
    settings = _FakeSettings({})  # type: ignore[arg-type]
    result = get_anchor_qnames(["project/unknown"], settings)  # type: ignore[arg-type]
    assert result == []


def test_get_anchor_qnames_empty_group_list() -> None:
    settings = _FakeSettings({"project/uw-ios-app": ["A.B"]})  # type: ignore[arg-type]
    result = get_anchor_qnames([], settings)  # type: ignore[arg-type]
    assert result == []
