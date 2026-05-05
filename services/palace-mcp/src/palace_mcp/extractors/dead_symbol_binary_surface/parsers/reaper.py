"""Explicit Reaper no-op parser for dead_symbol_binary_surface v1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ReaperPlatform(str, Enum):
    """Platform variants supported by the no-op skip path."""

    IOS = "ios"
    ANDROID = "android"


class ReaperSkipReason(str, Enum):
    """Documented reasons for returning a no-op result."""

    REAPER_REPORT_UNAVAILABLE = "reaper_report_unavailable"


@dataclass(frozen=True)
class ReaperParseResult:
    """No-op parser result for missing/unsupported Reaper report inputs."""

    platform: ReaperPlatform
    skip_reason: ReaperSkipReason
    findings: tuple[()] = ()
    parser_warnings: tuple[str, ...] = ()
    synthetic_candidate_count: int = 0
    android_alternative_selected: bool = False


def parse_reaper_report(
    *,
    platform: ReaperPlatform,
    report_path: Path | None,
    android_alternative_spike_path: Path | None = None,
) -> ReaperParseResult:
    """Return the documented v1 no-op skip result.

    Reaper currently has no verified offline report-file contract for either
    iOS or Android. The parser therefore returns an explicit skip result and
    does not fabricate synthetic candidates.
    """

    del report_path
    del android_alternative_spike_path
    return ReaperParseResult(
        platform=platform,
        skip_reason=ReaperSkipReason.REAPER_REPORT_UNAVAILABLE,
    )
