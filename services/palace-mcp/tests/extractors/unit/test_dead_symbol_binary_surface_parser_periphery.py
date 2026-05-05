"""Unit tests for dead_symbol_binary_surface Periphery parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    CandidateState,
    DeadSymbolKind,
    SkipReason,
)
from palace_mcp.extractors.dead_symbol_binary_surface.parsers.periphery import (
    PeripherySkipRule,
    parse_periphery_fixture,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "dead-symbol-binary-surface-mini-project"
    / "periphery"
)
RAW_FIXTURE = FIXTURE_ROOT / "periphery-3.7.4-swiftpm.json"
CONTRACT_FIXTURE = FIXTURE_ROOT / "contract.json"


def _load_raw_fixture() -> list[dict[str, Any]]:
    return json.loads(RAW_FIXTURE.read_text(encoding="utf-8"))


def _load_contract_fixture() -> dict[str, Any]:
    return json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))


def _write_fixture(
    tmp_path: Path,
    *,
    raw: list[dict[str, Any]] | None = None,
    contract: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    raw_path = tmp_path / "periphery.json"
    contract_path = tmp_path / "contract.json"
    raw_path.write_text(
        json.dumps(_load_raw_fixture() if raw is None else raw),
        encoding="utf-8",
    )
    contract_path.write_text(
        json.dumps(_load_contract_fixture() if contract is None else contract),
        encoding="utf-8",
    )
    return raw_path, contract_path


def _raw_item_by_name(name: str) -> dict[str, Any]:
    for item in _load_raw_fixture():
        if item["name"] == name:
            return item
    raise AssertionError(f"fixture item {name!r} not found")


def test_parse_periphery_fixture_requires_tool_output_schema_version(
    tmp_path: Path,
) -> None:
    contract = _load_contract_fixture()
    contract.pop("tool_output_schema_version")
    raw_path, contract_path = _write_fixture(tmp_path, contract=contract)

    with pytest.raises(ValueError, match="tool_output_schema_version"):
        parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)


def test_parse_periphery_fixture_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    contract = _load_contract_fixture()
    contract["unexpected_top_level_key"] = True
    raw_path, contract_path = _write_fixture(tmp_path, contract=contract)

    with pytest.raises(ValueError, match="unexpected_top_level_key"):
        parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)


def test_parse_periphery_unused_swift_class(tmp_path: Path) -> None:
    raw_path, contract_path = _write_fixture(tmp_path)

    result = parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)

    finding = next(
        item for item in result.findings if item.display_name == "UnusedHelper"
    )
    assert finding.kind is DeadSymbolKind.CLASS
    assert finding.candidate_state is CandidateState.UNUSED_CANDIDATE
    assert finding.symbol_key == "UnusedHelper"
    assert finding.module_name == "DeadSymbolMiniCore"
    assert finding.source_file == "Sources/DeadSymbolMiniCore/UnusedHelper.swift"
    assert finding.source_line == 1
    assert finding.source_column == 13


def test_parse_periphery_unused_swift_function(tmp_path: Path) -> None:
    raw = _load_raw_fixture()
    raw.append(
        {
            "ids": ["s:18DeadSymbolMiniCore12UnusedHelperC7refreshyyF"],
            "name": "UnusedHelper.refresh()",
            "modifiers": [],
            "location": "Sources/DeadSymbolMiniCore/UnusedHelper.swift:10:5",
            "attributes": [],
            "accessibility": "internal",
            "hints": ["unused"],
            "kind": "function",
            "modules": ["DeadSymbolMiniCore"],
        }
    )
    raw_path, contract_path = _write_fixture(tmp_path, raw=raw)

    result = parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)

    finding = next(
        item
        for item in result.findings
        if item.display_name == "UnusedHelper.refresh()"
    )
    assert finding.kind is DeadSymbolKind.FUNCTION
    assert finding.symbol_key == "UnusedHelper.refresh()"
    assert finding.tool_symbol_id == "s:18DeadSymbolMiniCore12UnusedHelperC7refreshyyF"


def test_parse_periphery_unused_swift_property(tmp_path: Path) -> None:
    raw = _load_raw_fixture()
    raw.append(
        {
            "ids": ["s:18DeadSymbolMiniCore12UnusedHelperC7counterSivp"],
            "name": "UnusedHelper.counter",
            "modifiers": [],
            "location": "Sources/DeadSymbolMiniCore/UnusedHelper.swift:11:9",
            "attributes": [],
            "accessibility": "internal",
            "hints": ["unused"],
            "kind": "property",
            "modules": ["DeadSymbolMiniCore"],
        }
    )
    raw_path, contract_path = _write_fixture(tmp_path, raw=raw)

    result = parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)

    finding = next(
        item for item in result.findings if item.display_name == "UnusedHelper.counter"
    )
    assert finding.kind is DeadSymbolKind.PROPERTY
    assert finding.symbol_key == "UnusedHelper.counter"


def test_parse_periphery_public_symbol_retained_not_unused(tmp_path: Path) -> None:
    raw_path, contract_path = _write_fixture(tmp_path)

    result = parse_periphery_fixture(
        report_path=raw_path,
        contract_path=contract_path,
        retain_public=True,
    )

    finding = next(
        item for item in result.findings if item.display_name == "PublicButUnused"
    )
    assert finding.candidate_state is CandidateState.RETAINED_PUBLIC_API


def test_parse_periphery_generated_path_skipped_by_skiplist(tmp_path: Path) -> None:
    raw_path, contract_path = _write_fixture(tmp_path)

    result = parse_periphery_fixture(
        report_path=raw_path,
        contract_path=contract_path,
        skip_rules=(
            PeripherySkipRule(
                path_glob="**/Generated/*.swift",
                skip_reason=SkipReason.GENERATED_CODE,
            ),
        ),
    )

    finding = next(
        item for item in result.findings if item.display_name == "AutoGeneratedToken"
    )
    assert finding.candidate_state is CandidateState.SKIPPED
    assert finding.skip_reason is SkipReason.GENERATED_CODE


def test_parse_periphery_objc_dynamic_entry_skipped_by_skiplist(tmp_path: Path) -> None:
    raw = [
        {
            "ids": ["s:18DeadSymbolMiniCore11ObjcBridgeC6invokeyyF"],
            "name": "ObjcBridge.invoke()",
            "modifiers": ["dynamic"],
            "location": "Sources/DeadSymbolMiniCore/ObjcBridge.swift:7:5",
            "attributes": ["@objc"],
            "accessibility": "internal",
            "hints": ["unused"],
            "kind": "function",
            "modules": ["DeadSymbolMiniCore"],
        }
    ]
    raw_path, contract_path = _write_fixture(tmp_path, raw=raw)

    result = parse_periphery_fixture(
        report_path=raw_path,
        contract_path=contract_path,
        skip_rules=(
            PeripherySkipRule(
                attribute_contains="@objc",
                skip_reason=SkipReason.DYNAMIC_ENTRY_POINT,
            ),
        ),
    )

    assert len(result.findings) == 1
    assert result.findings[0].candidate_state is CandidateState.SKIPPED
    assert result.findings[0].skip_reason is SkipReason.DYNAMIC_ENTRY_POINT


def test_parse_periphery_malformed_finding_emits_warning_not_crash(
    tmp_path: Path,
) -> None:
    raw = [
        _raw_item_by_name("UnusedHelper"),
        {
            "ids": ["s:bad"],
            "name": "Broken",
            "modifiers": [],
            "attributes": [],
            "accessibility": "internal",
            "hints": ["unused"],
            "kind": "class",
            "modules": ["DeadSymbolMiniCore"],
        },
    ]
    raw_path, contract_path = _write_fixture(tmp_path, raw=raw)

    result = parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)

    assert len(result.findings) == 1
    assert result.findings[0].display_name == "UnusedHelper"
    assert len(result.parser_warnings) == 1
    assert "missing required keys" in result.parser_warnings[0]


def test_parse_periphery_normalized_symbol_key_is_deterministic(tmp_path: Path) -> None:
    raw = [
        {
            "ids": ["s:18DeadSymbolMiniCore12UnusedHelperC7refreshyyF"],
            "name": "UnusedHelper.refresh()",
            "modifiers": [],
            "location": "Sources/DeadSymbolMiniCore/UnusedHelper.swift:10:5",
            "attributes": [],
            "accessibility": "internal",
            "hints": ["unused"],
            "kind": "function",
            "modules": ["DeadSymbolMiniCore"],
        }
    ]
    raw_path, contract_path = _write_fixture(tmp_path, raw=raw)

    first = parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)
    second = parse_periphery_fixture(report_path=raw_path, contract_path=contract_path)

    assert first.findings[0].symbol_key == second.findings[0].symbol_key
    assert first.findings[0].tool_symbol_id == second.findings[0].tool_symbol_id
