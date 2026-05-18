"""Unit tests for reactive_dependency_tracer models and stable IDs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.foundation.models import Language, SCHEMA_VERSION_CURRENT
from palace_mcp.extractors.reactive_dependency_tracer.identifiers import (
    component_id_for,
    diagnostic_id_for,
    effect_id_for,
    edge_id_for,
    state_id_for,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    DiagnosticSeverity,
    Range,
    ReactiveComponent,
    ReactiveComponentKind,
    ReactiveConfidence,
    ReactiveDiagnostic,
    ReactiveDiagnosticCode,
    ReactiveEdge,
    ReactiveEdgeKind,
    ReactiveEffect,
    ReactiveEffectKind,
    ReactiveResolutionStatus,
    ReactiveState,
    ReactiveStateKind,
    TriggerExpressionKind,
)


def test_component_model_valid() -> None:
    component = ReactiveComponent(
        id=component_id_for(
            group_id="group/x",
            project="proj",
            commit_sha="abc123",
            language=Language.SWIFT,
            component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
            qualified_name="App.CounterView",
            file_path="Sources/App/CounterView.swift",
            start_line=1,
        ),
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        module_name="App",
        file_path="Sources/App/CounterView.swift",
        qualified_name="App.CounterView",
        display_name="CounterView",
        component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
        start_line=1,
        end_line=20,
        range=Range(start_line=1, start_col=1, end_line=20, end_col=1),
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        schema_version=SCHEMA_VERSION_CURRENT,
        source="extractor.reactive_dependency_tracer",
    )
    assert component.language is Language.SWIFT
    assert component.component_kind is ReactiveComponentKind.SWIFTUI_VIEW


def test_state_model_requires_wrapper_or_api_optional() -> None:
    state = ReactiveState(
        id=state_id_for(
            group_id="group/x",
            project="proj",
            commit_sha="abc123",
            language=Language.SWIFT,
            owner_qualified_name="App.CounterView",
            state_name="count",
            state_kind=ReactiveStateKind.STATE,
            file_path="Sources/App/CounterView.swift",
        ),
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        module_name="App",
        file_path="Sources/App/CounterView.swift",
        owner_qualified_name="App.CounterView",
        state_name="count",
        declared_type="Int",
        state_kind=ReactiveStateKind.STATE,
        wrapper_or_api="@State",
        macro_expansion_status="not_applicable",
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        confidence=ReactiveConfidence.HIGH,
        schema_version=SCHEMA_VERSION_CURRENT,
        source="extractor.reactive_dependency_tracer",
    )
    assert state.wrapper_or_api == "@State"


def test_effect_model_lifecycle_trigger_is_optional() -> None:
    effect = ReactiveEffect(
        id=effect_id_for(
            group_id="group/x",
            project="proj",
            commit_sha="abc123",
            language=Language.SWIFT,
            component_id="component-1",
            effect_kind=ReactiveEffectKind.TASK,
            file_path="Sources/App/CounterView.swift",
            start_line=10,
            callee_name="task",
        ),
        component_id="component-1",
        effect_kind=ReactiveEffectKind.TASK,
        callee_name="task",
        file_path="Sources/App/CounterView.swift",
        start_line=10,
        end_line=14,
        range=Range(start_line=10, start_col=5, end_line=14, end_col=6),
        trigger_expression_kind=None,
        resolution_status=ReactiveResolutionStatus.SYNTAX_HEURISTIC,
        confidence=ReactiveConfidence.MEDIUM,
        source="extractor.reactive_dependency_tracer",
        schema_version=SCHEMA_VERSION_CURRENT,
    )
    assert effect.trigger_expression_kind is None


def test_diagnostic_message_is_bounded() -> None:
    with pytest.raises(ValidationError, match="message_redacted"):
        ReactiveDiagnostic(
            id=diagnostic_id_for(
                group_id="group/x",
                project="proj",
                commit_sha="abc123",
                diagnostic_code=ReactiveDiagnosticCode.SWIFT_PARSE_FAILED,
                file_path="Sources/App/CounterView.swift",
                ref="c1",
                range=Range(start_line=1, start_col=1, end_line=1, end_col=2),
            ),
            group_id="group/x",
            project="proj",
            commit_sha="abc123",
            run_id="run-1",
            language=Language.SWIFT,
            file_path="Sources/App/CounterView.swift",
            ref="c1",
            diagnostic_code=ReactiveDiagnosticCode.SWIFT_PARSE_FAILED,
            severity=DiagnosticSeverity.WARNING,
            message_redacted="x" * 513,
            range=Range(start_line=1, start_col=1, end_line=1, end_col=2),
            source="extractor.reactive_dependency_tracer",
            schema_version=SCHEMA_VERSION_CURRENT,
        )


def test_edge_model_requires_trigger_kind_for_trigger_edges() -> None:
    with pytest.raises(ValidationError, match="trigger_expression_kind"):
        ReactiveEdge(
            id=edge_id_for(
                owner_component_id="component-1",
                edge_kind=ReactiveEdgeKind.TRIGGERS_EFFECT,
                source_id="state-1",
                target_id="effect-1",
                file_path="Sources/App/CounterView.swift",
                line=12,
            ),
            owner_component_id="component-1",
            edge_kind=ReactiveEdgeKind.TRIGGERS_EFFECT,
            source_id="state-1",
            target_id="effect-1",
            file_path="Sources/App/CounterView.swift",
            line=12,
            confidence=ReactiveConfidence.HIGH,
            access_path="count",
            binding_kind=None,
            trigger_expression_kind=None,
            resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        )


def test_models_are_frozen() -> None:
    component = ReactiveComponent(
        id="component-1",
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        module_name="App",
        file_path="Sources/App/CounterView.swift",
        qualified_name="App.CounterView",
        display_name="CounterView",
        component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
        start_line=1,
        end_line=20,
        range=Range(start_line=1, start_col=1, end_line=20, end_col=1),
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        schema_version=SCHEMA_VERSION_CURRENT,
        source="extractor.reactive_dependency_tracer",
    )
    with pytest.raises(ValidationError):
        component.display_name = "Other"  # type: ignore[misc]


def test_stable_ids_are_deterministic_and_identity_sensitive() -> None:
    first = component_id_for(
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
        qualified_name="App.CounterView",
        file_path="Sources/App/CounterView.swift",
        start_line=1,
    )
    second = component_id_for(
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
        qualified_name="App.CounterView",
        file_path="Sources/App/CounterView.swift",
        start_line=1,
    )
    changed = component_id_for(
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
        qualified_name="App.CounterView",
        file_path="Sources/App/CounterView.swift",
        start_line=2,
    )
    assert first == second
    assert first != changed


def test_range_rejects_reverse_coordinates() -> None:
    with pytest.raises(ValidationError, match="end_col"):
        Range(start_line=4, start_col=8, end_line=4, end_col=7)


def test_trigger_effect_edge_accepts_trigger_kind() -> None:
    edge = ReactiveEdge(
        id="edge-1",
        owner_component_id="component-1",
        edge_kind=ReactiveEdgeKind.TRIGGERS_EFFECT,
        source_id="state-1",
        target_id="effect-1",
        file_path="Sources/App/CounterView.swift",
        line=12,
        confidence=ReactiveConfidence.HIGH,
        access_path="count",
        binding_kind=None,
        trigger_expression_kind=TriggerExpressionKind.ON_CHANGE_OF,
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
    )
    assert edge.trigger_expression_kind is TriggerExpressionKind.ON_CHANGE_OF
