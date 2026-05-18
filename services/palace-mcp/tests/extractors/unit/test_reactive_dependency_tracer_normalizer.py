"""Unit tests for reactive_dependency_tracer Swift normalization."""

from __future__ import annotations

import json
from pathlib import Path

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    ReactiveDiagnosticCode,
    ReactiveEdgeKind,
    ReactiveEffectKind,
    ReactiveStateKind,
)
from palace_mcp.extractors.reactive_dependency_tracer.normalizer import (
    normalize_swift_helper_file,
)
from palace_mcp.extractors.reactive_dependency_tracer.swift_helper_contract import (
    parse_swift_helper_contract,
)


def _payload() -> dict[str, object]:
    return {
        "tool_name": "palace-swift-reactive-probe",
        "tool_version": "0.1.0",
        "schema_version": 1,
        "swift_syntax_version": "600.0.1",
        "swift_toolchain": "Swift 6.0",
        "files": [
            {
                "path": "Sources/App/CounterView.swift",
                "module_name": "App",
                "parse_status": "ok",
                "components": [
                    {
                        "component_ref": "c1",
                        "module_name": "App",
                        "component_kind": "swiftui_view",
                        "qualified_name": "App.CounterView",
                        "display_name": "CounterView",
                        "range": {
                            "start_line": 1,
                            "start_col": 1,
                            "end_line": 20,
                            "end_col": 1,
                        },
                        "resolution_status": "syntax_exact",
                    }
                ],
                "states": [
                    {
                        "state_ref": "s1",
                        "owner_component_ref": "c1",
                        "module_name": "App",
                        "state_name": "count",
                        "state_kind": "state",
                        "wrapper_or_api": "@State",
                        "declared_type": "Int",
                        "range": {
                            "start_line": 3,
                            "start_col": 5,
                            "end_line": 3,
                            "end_col": 22,
                        },
                        "resolution_status": "syntax_exact",
                    }
                ],
                "effects": [
                    {
                        "effect_ref": "e1",
                        "owner_component_ref": "c1",
                        "effect_kind": "on_change",
                        "callee_name": "onChange",
                        "trigger_expression_kind": "on_change_of",
                        "range": {
                            "start_line": 10,
                            "start_col": 9,
                            "end_line": 14,
                            "end_col": 10,
                        },
                        "resolution_status": "syntax_exact",
                    }
                ],
                "edges": [
                    {
                        "edge_ref": "r1",
                        "edge_kind": "triggers_effect",
                        "from_ref": "s1",
                        "to_ref": "e1",
                        "owner_component_ref": "c1",
                        "access_path": "count",
                        "binding_kind": None,
                        "trigger_expression_kind": "on_change_of",
                        "range": {
                            "start_line": 10,
                            "start_col": 19,
                            "end_line": 10,
                            "end_col": 24,
                        },
                        "confidence_hint": "high",
                        "resolution_status": "syntax_exact",
                    }
                ],
                "diagnostics": [],
            }
        ],
        "run_diagnostics": [],
    }


def test_normalize_swift_file_builds_domain_records(tmp_path: Path) -> None:
    doc = parse_swift_helper_contract(json.dumps(_payload()), repo_root=tmp_path)

    normalized = normalize_swift_helper_file(
        doc.files[0],
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        run_id="run-1",
        language=Language.SWIFT,
    )

    assert len(normalized.components) == 1
    assert len(normalized.states) == 1
    assert len(normalized.effects) == 1
    assert len(normalized.edges) == 2
    assert normalized.states[0].state_kind is ReactiveStateKind.STATE
    assert normalized.effects[0].effect_kind is ReactiveEffectKind.ON_CHANGE
    edge_kinds = {edge.edge_kind for edge in normalized.edges}
    assert ReactiveEdgeKind.DECLARES_STATE in edge_kinds
    assert ReactiveEdgeKind.TRIGGERS_EFFECT in edge_kinds


def test_normalizer_preserves_paths_and_ranges(tmp_path: Path) -> None:
    doc = parse_swift_helper_contract(json.dumps(_payload()), repo_root=tmp_path)

    normalized = normalize_swift_helper_file(
        doc.files[0],
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        run_id="run-1",
        language=Language.SWIFT,
    )

    component = normalized.components[0]
    assert component.file_path == "Sources/App/CounterView.swift"
    assert component.range.start_line == 1
    assert component.range.end_line == 20


def test_lifecycle_effect_does_not_create_trigger_edge_without_explicit_trigger(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["files"][0]["effects"] = [  # type: ignore[index]
        {
            "effect_ref": "e2",
            "owner_component_ref": "c1",
            "effect_kind": "task",
            "callee_name": "task",
            "trigger_expression_kind": None,
            "range": {
                "start_line": 15,
                "start_col": 9,
                "end_line": 17,
                "end_col": 10,
            },
            "resolution_status": "syntax_exact",
        }
    ]
    payload["files"][0]["edges"] = []  # type: ignore[index]
    doc = parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)

    normalized = normalize_swift_helper_file(
        doc.files[0],
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        run_id="run-1",
        language=Language.SWIFT,
    )

    assert len(normalized.effects) == 1
    assert all(
        edge.edge_kind is not ReactiveEdgeKind.TRIGGERS_EFFECT
        for edge in normalized.edges
    )


def test_missing_symbol_key_emits_diagnostic(tmp_path: Path) -> None:
    doc = parse_swift_helper_contract(json.dumps(_payload()), repo_root=tmp_path)

    normalized = normalize_swift_helper_file(
        doc.files[0],
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        run_id="run-1",
        language=Language.SWIFT,
        component_symbol_keys={},
    )

    codes = {diagnostic.diagnostic_code for diagnostic in normalized.diagnostics}
    assert ReactiveDiagnosticCode.SYMBOL_CORRELATION_UNAVAILABLE in codes
