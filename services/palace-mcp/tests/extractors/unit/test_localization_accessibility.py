"""Unit tests for localization_accessibility extractor (GIM-275)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_FIXTURE_ROOT = (
    Path(__file__).parent.parent / "fixtures" / "loc-a11y-fixture"
)
_RULES_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "src"
    / "palace_mcp"
    / "extractors"
    / "localization_accessibility"
    / "semgrep_rules"
)


# ---------------------------------------------------------------------------
# Phase 2.1 — Registration
# ---------------------------------------------------------------------------


def test_localization_accessibility_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("localization_accessibility")
    assert extractor is not None
    assert extractor.name == "localization_accessibility"
    assert extractor.description


def test_localization_accessibility_has_indexes() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS["localization_accessibility"]
    index_text = " ".join(extractor.indexes)
    assert "LocaleResource" in index_text
    assert "HardcodedString" in index_text
    assert "A11yMissing" in index_text


# ---------------------------------------------------------------------------
# Phase 2.2 — xcstrings parser
# ---------------------------------------------------------------------------


def test_xcstrings_parser_basic() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.xcstrings import (
        parse_xcstrings,
    )

    catalog = {
        "version": "1.0",
        "sourceLanguage": "en",
        "strings": {
            "hello_world": {
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "Hello World"}},
                    "ru": {"stringUnit": {"state": "translated", "value": "Привет мир"}},
                }
            },
            "goodbye": {
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "Goodbye"}},
                }
            },
        },
    }
    source_file = "App/Localizable.xcstrings"
    rows = parse_xcstrings(catalog, source_file=source_file)
    by_locale = {r.locale: r for r in rows}
    assert "en" in by_locale
    assert "ru" in by_locale
    assert by_locale["en"].key_count == 2
    assert by_locale["ru"].key_count == 1
    assert by_locale["en"].source == source_file
    assert by_locale["en"].surface == "ios"


def test_xcstrings_parser_empty_catalog() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.xcstrings import (
        parse_xcstrings,
    )

    catalog = {"version": "1.0", "sourceLanguage": "en", "strings": {}}
    rows = parse_xcstrings(catalog, source_file="App/Empty.xcstrings")
    assert rows == []


def test_xcstrings_parser_missing_localizations() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.xcstrings import (
        parse_xcstrings,
    )

    catalog = {
        "version": "1.0",
        "sourceLanguage": "en",
        "strings": {
            "key_no_locs": {},
        },
    }
    rows = parse_xcstrings(catalog, source_file="App/X.xcstrings")
    # no localizations → no rows
    assert rows == []


# ---------------------------------------------------------------------------
# Phase 2.2 — Localizable.strings parser
# ---------------------------------------------------------------------------


def test_localizable_strings_parser_basic() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.localizable_strings import (
        parse_localizable_strings,
    )

    content = """
/* comment */
"greeting" = "Hello";
"farewell" = "Goodbye";
"app_name" = "MyApp";
"""
    row = parse_localizable_strings(content, locale="en", source_file="en.lproj/Localizable.strings")
    assert row.locale == "en"
    assert row.key_count == 3
    assert row.surface == "ios"
    assert "en.lproj" in row.source


def test_localizable_strings_parser_ignores_comments() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.localizable_strings import (
        parse_localizable_strings,
    )

    content = '/* comment only */\n'
    row = parse_localizable_strings(content, locale="de", source_file="de.lproj/Localizable.strings")
    assert row.key_count == 0


def test_localizable_strings_parser_escaped_quotes() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.localizable_strings import (
        parse_localizable_strings,
    )

    content = r'"key_with_quote" = "He said \"hello\"";' + "\n"
    row = parse_localizable_strings(content, locale="en", source_file="en.lproj/Localizable.strings")
    assert row.key_count == 1


# ---------------------------------------------------------------------------
# Phase 2.2 — Android strings.xml parser
# ---------------------------------------------------------------------------


def test_android_strings_parser_basic() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.android_strings import (
        parse_android_strings_xml,
    )

    xml = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">My App</string>
    <string name="greeting">Hello</string>
    <string name="farewell">Goodbye</string>
</resources>"""
    row = parse_android_strings_xml(xml, locale="en", source_file="res/values/strings.xml")
    assert row.locale == "en"
    assert row.key_count == 3
    assert row.surface == "android"


def test_android_strings_parser_locale_dir() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.android_strings import (
        parse_android_strings_xml,
    )

    xml = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="greeting">Привет</string>
</resources>"""
    row = parse_android_strings_xml(xml, locale="ru", source_file="res/values-ru/strings.xml")
    assert row.locale == "ru"
    assert row.key_count == 1


def test_android_strings_parser_ignores_non_string() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.android_strings import (
        parse_android_strings_xml,
    )

    xml = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="key1">Value</string>
    <plurals name="items">
        <item quantity="one">item</item>
    </plurals>
    <string-array name="colors">
        <item>red</item>
    </string-array>
</resources>"""
    row = parse_android_strings_xml(xml, locale="en", source_file="res/values/strings.xml")
    # only <string> elements count
    assert row.key_count == 1


# ---------------------------------------------------------------------------
# Phase 2.2 — Locale coverage computation (rule 1)
# ---------------------------------------------------------------------------


def test_locale_coverage_basic() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.coverage import (
        compute_coverage,
        LocaleResource,
    )

    resources = [
        LocaleResource(locale="en", key_count=100, source="en.lproj/Localizable.strings", surface="ios"),
        LocaleResource(locale="ru", key_count=80, source="ru.lproj/Localizable.strings", surface="ios"),
        LocaleResource(locale="es", key_count=60, source="es.lproj/Localizable.strings", surface="ios"),
    ]
    result = compute_coverage(resources, base_locale="en")
    by_locale = {r.locale: r for r in result}
    assert by_locale["en"].coverage_pct == pytest.approx(100.0)
    assert by_locale["ru"].coverage_pct == pytest.approx(80.0)
    assert by_locale["es"].coverage_pct == pytest.approx(60.0)


def test_locale_coverage_missing_base() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.coverage import (
        compute_coverage,
        LocaleResource,
    )

    resources = [
        LocaleResource(locale="ru", key_count=50, source="src.strings", surface="ios"),
    ]
    result = compute_coverage(resources, base_locale="en")
    # base locale not present → coverage undefined → 0%
    assert result[0].coverage_pct == pytest.approx(0.0)


def test_locale_coverage_zero_base_keys() -> None:
    from palace_mcp.extractors.localization_accessibility.parsers.coverage import (
        compute_coverage,
        LocaleResource,
    )

    resources = [
        LocaleResource(locale="en", key_count=0, source="src.strings", surface="ios"),
        LocaleResource(locale="ru", key_count=5, source="src.strings", surface="ios"),
    ]
    result = compute_coverage(resources, base_locale="en")
    by_locale = {r.locale: r for r in result}
    assert by_locale["ru"].coverage_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Phase 2.3 — Semgrep helper
# ---------------------------------------------------------------------------


def _semgrep_bin() -> str:
    import shutil

    venv_semgrep = Path(sys.executable).parent / "semgrep"
    if venv_semgrep.exists():
        return str(venv_semgrep)
    found = shutil.which("semgrep")
    assert found is not None, "semgrep not found; run: uv add semgrep"
    return found


def _run_semgrep_on_rule(rule_file: Path, target: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            _semgrep_bin(),
            "--config",
            str(rule_file),
            "--json",
            "--quiet",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return data.get("results", [])


def _check_ids(findings: list[dict[str, Any]]) -> set[str]:
    return {str(f.get("check_id", "")).split(".")[-1] for f in findings}


# ---------------------------------------------------------------------------
# Phase 2.3 — Rule 2: loc.hardcoded_swiftui
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_RULES_DIR / "loc_hardcoded_swiftui.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_hardcoded_swiftui_bad_fixture_triggers() -> None:
    bad_dir = _FIXTURE_ROOT / "hardcoded-swiftui" / "bad"
    rule_file = _RULES_DIR / "loc_hardcoded_swiftui.yaml"
    findings = _run_semgrep_on_rule(rule_file, bad_dir)
    assert len(findings) >= 1, "Expected ≥1 finding on bad SwiftUI fixture"


@pytest.mark.skipif(
    not (_RULES_DIR / "loc_hardcoded_swiftui.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_hardcoded_swiftui_good_fixture_silent() -> None:
    good_dir = _FIXTURE_ROOT / "hardcoded-swiftui" / "good"
    rule_file = _RULES_DIR / "loc_hardcoded_swiftui.yaml"
    findings = _run_semgrep_on_rule(rule_file, good_dir)
    # Text(verbatim:) must NOT be flagged
    assert len(findings) == 0, f"False positive on good SwiftUI fixture: {findings}"


# ---------------------------------------------------------------------------
# Phase 2.3 — Rule 3: loc.hardcoded_compose
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_RULES_DIR / "loc_hardcoded_compose.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_hardcoded_compose_bad_fixture_triggers() -> None:
    bad_dir = _FIXTURE_ROOT / "hardcoded-compose" / "bad"
    rule_file = _RULES_DIR / "loc_hardcoded_compose.yaml"
    findings = _run_semgrep_on_rule(rule_file, bad_dir)
    assert len(findings) >= 1, "Expected ≥1 finding on bad Compose fixture"


@pytest.mark.skipif(
    not (_RULES_DIR / "loc_hardcoded_compose.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_hardcoded_compose_good_fixture_silent() -> None:
    good_dir = _FIXTURE_ROOT / "hardcoded-compose" / "good"
    rule_file = _RULES_DIR / "loc_hardcoded_compose.yaml"
    findings = _run_semgrep_on_rule(rule_file, good_dir)
    assert len(findings) == 0, f"False positive on good Compose fixture: {findings}"


# ---------------------------------------------------------------------------
# Phase 2.3 — Rule 4: loc.hardcoded_uikit
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_RULES_DIR / "loc_hardcoded_uikit.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_hardcoded_uikit_bad_fixture_triggers() -> None:
    bad_dir = _FIXTURE_ROOT / "hardcoded-uikit" / "bad"
    rule_file = _RULES_DIR / "loc_hardcoded_uikit.yaml"
    findings = _run_semgrep_on_rule(rule_file, bad_dir)
    assert len(findings) >= 1, "Expected ≥1 finding on bad UIKit fixture"


@pytest.mark.skipif(
    not (_RULES_DIR / "loc_hardcoded_uikit.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_hardcoded_uikit_good_fixture_silent() -> None:
    good_dir = _FIXTURE_ROOT / "hardcoded-uikit" / "good"
    rule_file = _RULES_DIR / "loc_hardcoded_uikit.yaml"
    findings = _run_semgrep_on_rule(rule_file, good_dir)
    assert len(findings) == 0, f"False positive on good UIKit fixture: {findings}"


# ---------------------------------------------------------------------------
# Phase 2.4 — Rule 5: a11y.missing_label_swiftui
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_RULES_DIR / "a11y_missing_label_swiftui.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_a11y_missing_swiftui_bad_fixture_triggers() -> None:
    bad_dir = _FIXTURE_ROOT / "a11y-missing-swiftui" / "bad"
    rule_file = _RULES_DIR / "a11y_missing_label_swiftui.yaml"
    findings = _run_semgrep_on_rule(rule_file, bad_dir)
    assert len(findings) >= 1, "Expected ≥1 finding on bad SwiftUI a11y fixture"


@pytest.mark.skipif(
    not (_RULES_DIR / "a11y_missing_label_swiftui.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_a11y_missing_swiftui_good_fixture_silent() -> None:
    good_dir = _FIXTURE_ROOT / "a11y-missing-swiftui" / "good"
    rule_file = _RULES_DIR / "a11y_missing_label_swiftui.yaml"
    findings = _run_semgrep_on_rule(rule_file, good_dir)
    assert len(findings) == 0, f"False positive on good SwiftUI a11y fixture: {findings}"


# ---------------------------------------------------------------------------
# Phase 2.4 — Rule 6: a11y.missing_compose
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_RULES_DIR / "a11y_missing_compose.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_a11y_missing_compose_bad_fixture_triggers() -> None:
    bad_dir = _FIXTURE_ROOT / "a11y-missing-compose" / "bad"
    rule_file = _RULES_DIR / "a11y_missing_compose.yaml"
    findings = _run_semgrep_on_rule(rule_file, bad_dir)
    assert len(findings) >= 1, "Expected ≥1 finding on bad Compose a11y fixture"


@pytest.mark.skipif(
    not (_RULES_DIR / "a11y_missing_compose.yaml").exists(),
    reason="semgrep rule not yet implemented",
)
def test_a11y_missing_compose_good_fixture_silent() -> None:
    good_dir = _FIXTURE_ROOT / "a11y-missing-compose" / "good"
    rule_file = _RULES_DIR / "a11y_missing_compose.yaml"
    findings = _run_semgrep_on_rule(rule_file, good_dir)
    assert len(findings) == 0, f"False positive on good Compose a11y fixture: {findings}"


# ---------------------------------------------------------------------------
# Phase 2.5 — Allowlist
# ---------------------------------------------------------------------------


def test_allowlist_filters_matching_strings(tmp_path: Path) -> None:
    from palace_mcp.extractors.localization_accessibility.rules.allowlist import (
        load_allowlist,
        is_allowlisted,
    )

    allowlist_file = tmp_path / ".gimle" / "loc-allowlist.txt"
    allowlist_file.parent.mkdir(parents=True)
    allowlist_file.write_text("Bitcoin\nEthereum\nSatoshi\n")

    allowlist = load_allowlist(tmp_path)
    assert is_allowlisted("Bitcoin", allowlist)
    assert is_allowlisted("Ethereum", allowlist)
    assert not is_allowlisted("Hello World", allowlist)


def test_allowlist_missing_file(tmp_path: Path) -> None:
    from palace_mcp.extractors.localization_accessibility.rules.allowlist import (
        load_allowlist,
    )

    allowlist = load_allowlist(tmp_path)
    assert allowlist == frozenset()


def test_allowlist_ignores_blank_lines(tmp_path: Path) -> None:
    from palace_mcp.extractors.localization_accessibility.rules.allowlist import (
        load_allowlist,
    )

    allowlist_file = tmp_path / ".gimle" / "loc-allowlist.txt"
    allowlist_file.parent.mkdir(parents=True)
    allowlist_file.write_text("Bitcoin\n\n  \nEthereum\n")

    allowlist = load_allowlist(tmp_path)
    assert len(allowlist) == 2


# ---------------------------------------------------------------------------
# Phase 2.7 — audit_contract
# ---------------------------------------------------------------------------


def test_audit_contract_returns_contract() -> None:
    from palace_mcp.extractors.localization_accessibility.extractor import (
        LocalizationAccessibilityExtractor,
    )

    extractor = LocalizationAccessibilityExtractor()
    contract = extractor.audit_contract()
    assert contract is not None
    assert contract.extractor_name == "localization_accessibility"
    assert "LocaleResource" in contract.query or "HardcodedString" in contract.query
