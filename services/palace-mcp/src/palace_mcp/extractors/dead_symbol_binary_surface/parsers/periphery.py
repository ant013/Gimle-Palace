"""Periphery JSON parser for dead_symbol_binary_surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, model_validator

from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    CandidateState,
    DeadSymbolKind,
    DeadSymbolLanguage,
    SkipReason,
)

_ALLOWED_CONTRACT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "tool_name",
        "tool_version",
        "output_format",
        "tool_output_schema_version",
        "captured_at",
        "capture_host",
        "fixture_project_root",
        "command",
        "raw_output_file",
        "result_count",
        "required_result_keys",
        "observed_values",
        "parser_contract",
        "expected_symbols",
    }
)
_SUPPORTED_KINDS: Final[dict[str, DeadSymbolKind]] = {
    "class": DeadSymbolKind.CLASS,
    "struct": DeadSymbolKind.STRUCT,
    "enum": DeadSymbolKind.ENUM,
    "protocol": DeadSymbolKind.PROTOCOL,
    "function": DeadSymbolKind.FUNCTION,
    "property": DeadSymbolKind.PROPERTY,
    "initializer": DeadSymbolKind.INITIALIZER,
    "typealias": DeadSymbolKind.TYPEALIAS,
}


class PeripherySkipRule(BaseModel):
    """Parser-local skip rule passed from extractor/fixtures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path_glob: str | None = None
    attribute_contains: str | None = None
    skip_reason: SkipReason

    @model_validator(mode="after")
    def _validate_selector(self) -> "PeripherySkipRule":
        if self.path_glob is None and self.attribute_contains is None:
            raise ValueError("skip rule requires path_glob or attribute_contains")
        return self


@dataclass(frozen=True)
class PeripheryFinding:
    """Normalized Periphery finding ready for correlation."""

    tool_symbol_id: str
    all_ids: tuple[str, ...]
    display_name: str
    symbol_key: str
    module_name: str
    language: DeadSymbolLanguage
    kind: DeadSymbolKind
    accessibility: str
    source_file: str
    source_line: int
    source_column: int
    attributes: tuple[str, ...]
    modifiers: tuple[str, ...]
    hints: tuple[str, ...]
    candidate_state: CandidateState
    skip_reason: SkipReason | None


@dataclass(frozen=True)
class PeripheryParseResult:
    """Output of parsing one Periphery fixture."""

    findings: tuple[PeripheryFinding, ...]
    parser_warnings: tuple[str, ...]


def parse_periphery_fixture(
    *,
    report_path: Path,
    contract_path: Path,
    retain_public: bool = False,
    skip_rules: tuple[PeripherySkipRule, ...] = (),
) -> PeripheryParseResult:
    """Parse a Periphery JSON fixture using its signed contract metadata."""

    contract = _load_contract(contract_path)
    raw_items = _load_raw_items(report_path)
    required_keys = tuple(_load_required_result_keys(contract))

    findings: list[PeripheryFinding] = []
    warnings: list[str] = []
    for index, raw_item in enumerate(raw_items):
        try:
            findings.append(
                _normalize_item(
                    raw_item=raw_item,
                    required_keys=required_keys,
                    retain_public=retain_public,
                    skip_rules=skip_rules,
                )
            )
        except ValueError as exc:
            warnings.append(
                f"item {index} missing required keys or invalid values: {exc}"
            )
    return PeripheryParseResult(
        findings=tuple(findings),
        parser_warnings=tuple(warnings),
    )


def _load_contract(contract_path: Path) -> dict[str, Any]:
    contract_raw = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(contract_raw, dict):
        raise ValueError("Periphery contract must be a JSON object")

    contract_keys = set(contract_raw)
    unexpected_keys = sorted(contract_keys - _ALLOWED_CONTRACT_KEYS)
    if unexpected_keys:
        unexpected = ", ".join(unexpected_keys)
        raise ValueError(f"unexpected top-level key(s): {unexpected}")
    if "tool_output_schema_version" not in contract_raw:
        raise ValueError("tool_output_schema_version is required")
    return contract_raw


def _load_required_result_keys(contract: dict[str, Any]) -> tuple[str, ...]:
    raw_keys = contract.get("required_result_keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValueError("required_result_keys must be a non-empty list")
    normalized: list[str] = []
    for item in raw_keys:
        if not isinstance(item, str):
            raise ValueError("required_result_keys entries must be strings")
        normalized.append(item)
    return tuple(normalized)


def _load_raw_items(report_path: Path) -> list[dict[str, Any]]:
    raw_payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, list):
        raise ValueError("Periphery raw report must be a top-level JSON array")
    if not all(isinstance(item, dict) for item in raw_payload):
        raise ValueError("Periphery raw report items must be JSON objects")
    return list(raw_payload)


def _normalize_item(
    *,
    raw_item: dict[str, Any],
    required_keys: tuple[str, ...],
    retain_public: bool,
    skip_rules: tuple[PeripherySkipRule, ...],
) -> PeripheryFinding:
    missing_keys = [key for key in required_keys if key not in raw_item]
    if missing_keys:
        raise ValueError(", ".join(sorted(missing_keys)))

    ids_raw = raw_item["ids"]
    modules_raw = raw_item["modules"]
    attributes_raw = raw_item["attributes"]
    modifiers_raw = raw_item["modifiers"]
    hints_raw = raw_item["hints"]
    location_raw = raw_item["location"]

    if (
        not isinstance(ids_raw, list)
        or not ids_raw
        or not all(isinstance(item, str) for item in ids_raw)
    ):
        raise ValueError("ids must be a non-empty string array")
    if (
        not isinstance(modules_raw, list)
        or not modules_raw
        or not all(isinstance(item, str) for item in modules_raw)
    ):
        raise ValueError("modules must be a non-empty string array")
    if not isinstance(attributes_raw, list) or not all(
        isinstance(item, str) for item in attributes_raw
    ):
        raise ValueError("attributes must be a string array")
    if not isinstance(modifiers_raw, list) or not all(
        isinstance(item, str) for item in modifiers_raw
    ):
        raise ValueError("modifiers must be a string array")
    if not isinstance(hints_raw, list) or not all(
        isinstance(item, str) for item in hints_raw
    ):
        raise ValueError("hints must be a string array")
    if not isinstance(location_raw, str):
        raise ValueError("location must be a string")

    display_name = _require_string(raw_item, "name")
    accessibility = _require_string(raw_item, "accessibility")
    kind = _normalize_kind(_require_string(raw_item, "kind"))
    module_name = modules_raw[0]
    source_file, source_line, source_column = _parse_location(location_raw)
    attributes = tuple(attributes_raw)
    skip_reason = _match_skip_rule(
        source_file=source_file,
        attributes=attributes,
        skip_rules=skip_rules,
    )
    candidate_state = _candidate_state_for(
        accessibility=accessibility,
        retain_public=retain_public,
        skip_reason=skip_reason,
    )

    return PeripheryFinding(
        tool_symbol_id=ids_raw[0],
        all_ids=tuple(ids_raw),
        display_name=display_name,
        symbol_key=_normalize_symbol_key(display_name),
        module_name=module_name,
        language=DeadSymbolLanguage.SWIFT,
        kind=kind,
        accessibility=accessibility,
        source_file=source_file,
        source_line=source_line,
        source_column=source_column,
        attributes=attributes,
        modifiers=tuple(modifiers_raw),
        hints=tuple(hints_raw),
        candidate_state=candidate_state,
        skip_reason=skip_reason,
    )


def _require_string(raw_item: dict[str, Any], key: str) -> str:
    value = raw_item.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _normalize_kind(raw_kind: str) -> DeadSymbolKind:
    return _SUPPORTED_KINDS.get(raw_kind, DeadSymbolKind.UNKNOWN)


def _parse_location(location: str) -> tuple[str, int, int]:
    source_file, line_raw, column_raw = location.rsplit(":", 2)
    line = int(line_raw)
    column = int(column_raw)
    if not source_file or line < 1 or column < 1:
        raise ValueError("location must be project-relative with 1-based line/column")
    return source_file, line, column


def _match_skip_rule(
    *,
    source_file: str,
    attributes: tuple[str, ...],
    skip_rules: tuple[PeripherySkipRule, ...],
) -> SkipReason | None:
    for rule in skip_rules:
        path_match = rule.path_glob is None or fnmatch(source_file, rule.path_glob)
        attribute_match = rule.attribute_contains is None or any(
            rule.attribute_contains in attribute for attribute in attributes
        )
        if path_match and attribute_match:
            return rule.skip_reason
    return None


def _candidate_state_for(
    *,
    accessibility: str,
    retain_public: bool,
    skip_reason: SkipReason | None,
) -> CandidateState:
    if skip_reason is not None:
        return CandidateState.SKIPPED
    if retain_public and accessibility == "public":
        return CandidateState.RETAINED_PUBLIC_API
    return CandidateState.UNUSED_CANDIDATE


def _normalize_symbol_key(display_name: str) -> str:
    return display_name.strip()
