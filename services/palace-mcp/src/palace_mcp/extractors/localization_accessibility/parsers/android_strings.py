"""Parser for Android res/values-XX/strings.xml files."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from palace_mcp.extractors.localization_accessibility.parsers.coverage import LocaleResource


def parse_android_strings_xml(
    xml_content: str,
    *,
    locale: str,
    source_file: str,
) -> LocaleResource:
    """Parse a strings.xml file text into a LocaleResource row.

    Only counts direct <string> elements (not <plurals>, <string-array>).
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return LocaleResource(locale=locale, key_count=0, source=source_file, surface="android")

    count = sum(1 for child in root if child.tag == "string")
    return LocaleResource(
        locale=locale,
        key_count=count,
        source=source_file,
        surface="android",
    )
