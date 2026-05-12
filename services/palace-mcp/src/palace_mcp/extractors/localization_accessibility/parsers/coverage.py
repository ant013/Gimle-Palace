"""Locale coverage computation — rule 1: loc.locale_coverage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocaleResource:
    """Per-locale string resource summary (before coverage enrichment)."""

    locale: str
    key_count: int
    source: str
    surface: str  # "ios" | "android"


@dataclass(frozen=True)
class LocaleCoverage:
    """Per-locale coverage result after base-locale comparison."""

    locale: str
    key_count: int
    source: str
    surface: str
    coverage_pct: float


def compute_coverage(
    resources: list[LocaleResource],
    *,
    base_locale: str = "en",
) -> list[LocaleCoverage]:
    """Compute coverage_pct for each resource relative to base_locale key count.

    When base_locale is absent or has 0 keys, coverage_pct = 0.0 for all.
    """
    base_count = next(
        (r.key_count for r in resources if r.locale == base_locale), 0
    )
    result: list[LocaleCoverage] = []
    for r in resources:
        if base_count > 0:
            pct = (r.key_count / base_count) * 100.0
        else:
            pct = 0.0
        result.append(
            LocaleCoverage(
                locale=r.locale,
                key_count=r.key_count,
                source=r.source,
                surface=r.surface,
                coverage_pct=pct,
            )
        )
    return result
