"""Parser for Apple .xcstrings (Xcode 15+ catalog format, JSON)."""

from __future__ import annotations

from typing import Any

from palace_mcp.extractors.localization_accessibility.parsers.coverage import (
    LocaleResource,
)


def parse_xcstrings(
    catalog: dict[str, Any],
    *,
    source_file: str,
) -> list[LocaleResource]:
    """Parse a loaded .xcstrings JSON dict into per-locale LocaleResource rows.

    Counts only entries that have a localization for the given locale.
    """
    strings: dict[str, Any] = catalog.get("strings", {})
    if not strings:
        return []

    locale_counts: dict[str, int] = {}
    for _key, entry in strings.items():
        if not isinstance(entry, dict):
            continue
        localizations = entry.get("localizations", {})
        if not isinstance(localizations, dict):
            continue
        for locale in localizations:
            locale_counts[locale] = locale_counts.get(locale, 0) + 1

    return [
        LocaleResource(
            locale=locale,
            key_count=count,
            source=source_file,
            surface="ios",
        )
        for locale, count in sorted(locale_counts.items())
    ]
