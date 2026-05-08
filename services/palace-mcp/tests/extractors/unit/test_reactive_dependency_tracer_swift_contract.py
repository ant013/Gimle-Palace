"""Unit tests for the reactive_dependency_tracer Swift helper contract parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from palace_mcp.extractors.reactive_dependency_tracer.models import (
    ReactiveDiagnosticCode,
    ReactiveEdgeKind,
)
from palace_mcp.extractors.reactive_dependency_tracer.swift_helper_contract import (
    MAX_EDGES_PER_FILE,
    MAX_FILES_PER_RUN,
    MAX_WARNINGS_PER_FILE,
    parse_swift_helper_contract,
)


def _valid_payload() -> dict[str, object]:
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
                "diagnostics": [
                    {
                        "code": "macro_unexpanded",
                        "severity": "info",
                        "ref": "c1",
                        "message": "macro-decorated declaration recorded without expansion",
                        "range": {
                            "start_line": 1,
                            "start_col": 1,
                            "end_line": 1,
                            "end_col": 12,
                        },
                    }
                ],
            }
        ],
        "run_diagnostics": [],
    }


def test_parse_valid_contract(tmp_path: Path) -> None:
    doc = parse_swift_helper_contract(
        json.dumps(_valid_payload()),
        repo_root=tmp_path,
    )
    assert doc.files[0].path == "Sources/App/CounterView.swift"
    assert doc.files[0].edges[0].edge_kind is ReactiveEdgeKind.TRIGGERS_EFFECT
    assert doc.files[0].diagnostics[0].code is ReactiveDiagnosticCode.MACRO_UNEXPANDED


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unexpected"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_unsupported_schema_version_rejected(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_duplicate_refs_rejected(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"][0]["components"].append(payload["files"][0]["components"][0])  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicate"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_dangling_edge_ref_rejected(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"][0]["edges"][0]["to_ref"] = "missing-effect"  # type: ignore[index]
    with pytest.raises(ValueError, match="dangling"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


@pytest.mark.parametrize(
    ("path_value", "message"),
    [
        ("", "path_empty"),
        ("../Secrets.swift", "path_parent_traversal"),
        ("Sources\\App\\CounterView.swift", "path_windows_separator"),
        ("/tmp/CounterView.swift", "path_absolute_outside_repo"),
        ("~/CounterView.swift", "path_absolute_outside_repo"),
    ],
)
def test_invalid_paths_rejected(tmp_path: Path, path_value: str, message: str) -> None:
    payload = _valid_payload()
    payload["files"][0]["path"] = path_value  # type: ignore[index]
    with pytest.raises(ValueError, match=message):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_unknown_edge_kind_rejected(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"][0]["edges"][0]["edge_kind"] = "mystery"  # type: ignore[index]
    with pytest.raises(ValueError, match="edge_kind"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_file_diagnostics_do_not_fail_document(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"][0]["diagnostics"].append(
        {
            "code": "swift_parse_failed",
            "severity": "warning",
            "ref": None,
            "message": "parse failed",
            "range": None,
        }
    )  # type: ignore[index]
    doc = parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)
    assert len(doc.files[0].diagnostics) == 2


def test_warning_bound_enforced(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"][0]["diagnostics"] = [payload["files"][0]["diagnostics"][0]] * (  # type: ignore[index]
        MAX_WARNINGS_PER_FILE + 1
    )
    with pytest.raises(ValueError, match="max warnings"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_edge_bound_enforced(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"][0]["edges"] = [payload["files"][0]["edges"][0]] * (  # type: ignore[index]
        MAX_EDGES_PER_FILE + 1
    )
    with pytest.raises(ValueError, match="max edges"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)


def test_file_bound_enforced(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["files"] = [payload["files"][0]] * (MAX_FILES_PER_RUN + 1)  # type: ignore[index]
    with pytest.raises(ValueError, match="max files"):
        parse_swift_helper_contract(json.dumps(payload), repo_root=tmp_path)
