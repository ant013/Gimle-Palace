"""Unit tests for dead_symbol_binary_surface Reaper parser."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.dead_symbol_binary_surface.parsers.reaper import (
    ReaperParseResult,
    ReaperPlatform,
    ReaperSkipReason,
    parse_reaper_report,
)


def test_reaper_ios_report_unavailable_returns_skip() -> None:
    result = parse_reaper_report(platform=ReaperPlatform.IOS, report_path=None)

    assert result.platform is ReaperPlatform.IOS
    assert result.skip_reason is ReaperSkipReason.REAPER_REPORT_UNAVAILABLE


def test_reaper_android_report_unavailable_returns_skip() -> None:
    result = parse_reaper_report(platform=ReaperPlatform.ANDROID, report_path=None)

    assert result.platform is ReaperPlatform.ANDROID
    assert result.skip_reason is ReaperSkipReason.REAPER_REPORT_UNAVAILABLE


def test_reaper_skip_contains_no_synthetic_candidates() -> None:
    result = parse_reaper_report(platform=ReaperPlatform.IOS, report_path=None)

    assert result.findings == ()
    assert result.synthetic_candidate_count == 0


def test_reaper_skip_does_not_fail_periphery_only_run() -> None:
    result = parse_reaper_report(platform=ReaperPlatform.IOS, report_path=None)

    assert isinstance(result, ReaperParseResult)
    assert result.parser_warnings == ()


def test_android_alternative_not_selected_without_spike_file(tmp_path: Path) -> None:
    missing_spike = tmp_path / "android-alternative-spike.md"
    result = parse_reaper_report(
        platform=ReaperPlatform.ANDROID,
        report_path=None,
        android_alternative_spike_path=missing_spike,
    )

    assert result.android_alternative_selected is False
    assert result.skip_reason is ReaperSkipReason.REAPER_REPORT_UNAVAILABLE
