"""Unit tests for the normalized Instruments parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from palace_mcp.extractors.base import ExtractorRuntimeError
from palace_mcp.extractors.hot_path_profiler.parsers.instruments import (
    parse_instruments_trace,
)

_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "hot-path-fixture"
    / "synthetic"
    / "instruments-stub.json"
)


def test_parse_instruments_trace_returns_summary_and_samples() -> None:
    summary, samples = parse_instruments_trace(_FIXTURE)

    assert summary.trace_id == "synthetic-instruments"
    assert summary.total_cpu_samples == 1000
    assert summary.total_wall_ms == 640
    assert summary.hot_function_count == 3
    assert [sample.symbol_name for sample in samples] == [
        "WalletApp.AppDelegate.bootstrap()",
        "WalletApp.HomeViewModel.loadDashboard()",
        "WalletApp.PriceFormatter.formatPrice(_:)",
    ]
    assert samples[0].cpu_share == pytest.approx(0.38)
    assert samples[1].wall_share == pytest.approx(170 / 640)


def test_parse_instruments_trace_raises_for_missing_samples(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"trace_id": "broken"}), encoding="utf-8")

    with pytest.raises(ExtractorRuntimeError, match="samples"):
        parse_instruments_trace(path)
