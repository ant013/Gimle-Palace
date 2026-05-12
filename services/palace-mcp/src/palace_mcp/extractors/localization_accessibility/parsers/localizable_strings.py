"""Parser for Apple legacy Localizable.strings (key = "value"; format)."""

from __future__ import annotations

import re

from palace_mcp.extractors.localization_accessibility.parsers.coverage import LocaleResource

# Matches: "key" = "value"; — handles escaped quotes inside value
_ENTRY_RE = re.compile(
    r'"(?:[^"\\]|\\.)*"\s*=\s*"(?:[^"\\]|\\.)*"\s*;',
    re.MULTILINE,
)


def parse_localizable_strings(
    content: str,
    *,
    locale: str,
    source_file: str,
) -> LocaleResource:
    """Parse the text of a Localizable.strings file into a LocaleResource row."""
    matches = _ENTRY_RE.findall(content)
    return LocaleResource(
        locale=locale,
        key_count=len(matches),
        source=source_file,
        surface="ios",
    )
