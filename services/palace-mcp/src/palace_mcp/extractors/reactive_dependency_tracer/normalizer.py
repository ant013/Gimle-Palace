"""Normalization from Swift helper records into reactive domain models."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Mapping

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.confidence import (
    score_edge_confidence,
    score_effect_confidence,
    score_state_confidence,
)
from palace_mcp.extractors.reactive_dependency_tracer.diagnostics import (
    build_diagnostic,
)
from palace_mcp.extractors.reactive_dependency_tracer.identifiers import (
    component_id_for,
    edge_id_for,
    effect_id_for,
    state_id_for,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    DiagnosticSeverity,
    MacroExpansionStatus,
    ReactiveComponent,
    ReactiveDiagnostic,
    ReactiveDiagnosticCode,
    ReactiveEdge,
    ReactiveEdgeKind,
    ReactiveEffect,
    ReactiveState,
)
from palace_mcp.extractors.reactive_dependency_tracer.swift_helper_contract import (
    SwiftHelperFile,
)


@dataclass(frozen=True)
class NormalizedReactiveFile:
    """Normalized domain records for one helper file."""

    file_path: str | None
    language: Language
    components: tuple[ReactiveComponent, ...]
    states: tuple[ReactiveState, ...]
    effects: tuple[ReactiveEffect, ...]
    edges: tuple[ReactiveEdge, ...]
    diagnostics: tuple[ReactiveDiagnostic, ...]
    ref_to_node_id: Mapping[str, str]
    replace_existing_facts: bool = field(default=True)


def normalize_swift_helper_file(
    helper_file: SwiftHelperFile,
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    run_id: str,
    language: Language,
    component_symbol_keys: Mapping[str, str] | None = None,
) -> NormalizedReactiveFile:
    """Normalize one validated helper file into domain records."""

    components: list[ReactiveComponent] = []
    states: list[ReactiveState] = []
    effects: list[ReactiveEffect] = []
    edges: list[ReactiveEdge] = []
    diagnostics: list[ReactiveDiagnostic] = []

    component_ids: dict[str, str] = {}
    component_qualified_names: dict[str, str] = {}
    state_ids: dict[str, str] = {}
    effect_ids: dict[str, str] = {}
    ref_to_node_id: dict[str, str] = {}

    for component in helper_file.components:
        component_id = component_id_for(
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            language=language,
            component_kind=component.component_kind,
            qualified_name=component.qualified_name,
            file_path=helper_file.path,
            start_line=component.range.start_line,
        )
        component_ids[component.component_ref] = component_id
        component_qualified_names[component.component_ref] = component.qualified_name
        ref_to_node_id[component.component_ref] = component_id
        components.append(
            ReactiveComponent(
                id=component_id,
                group_id=group_id,
                project=project,
                commit_sha=commit_sha,
                language=language,
                module_name=component.module_name,
                file_path=helper_file.path,
                qualified_name=component.qualified_name,
                display_name=component.display_name,
                component_kind=component.component_kind,
                start_line=component.range.start_line,
                end_line=component.range.end_line,
                range=component.range,
                resolution_status=component.resolution_status,
            )
        )
        if (
            component_symbol_keys is not None
            and component.component_ref not in component_symbol_keys
        ):
            diagnostics.append(
                build_diagnostic(
                    group_id=group_id,
                    project=project,
                    commit_sha=commit_sha,
                    run_id=run_id,
                    language=language,
                    diagnostic_code=ReactiveDiagnosticCode.SYMBOL_CORRELATION_UNAVAILABLE,
                    severity=DiagnosticSeverity.INFO,
                    file_path=helper_file.path,
                    ref=component.component_ref,
                    range=component.range,
                    message=(
                        "Exact symbol correlation is unavailable for this reactive component"
                    ),
                )
            )

    for state in helper_file.states:
        owner_name = component_qualified_names[state.owner_component_ref]
        state_id = state_id_for(
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            language=language,
            owner_qualified_name=owner_name,
            state_name=state.state_name,
            state_kind=state.state_kind,
            file_path=helper_file.path,
        )
        state_ids[state.state_ref] = state_id
        ref_to_node_id[state.state_ref] = state_id
        confidence = score_state_confidence(
            state_kind=state.state_kind,
            resolution_status=state.resolution_status,
        )
        states.append(
            ReactiveState(
                id=state_id,
                group_id=group_id,
                project=project,
                commit_sha=commit_sha,
                language=language,
                module_name=state.module_name,
                file_path=helper_file.path,
                owner_qualified_name=owner_name,
                state_name=state.state_name,
                declared_type=state.declared_type,
                state_kind=state.state_kind,
                wrapper_or_api=state.wrapper_or_api,
                macro_expansion_status=(
                    MacroExpansionStatus.NOT_EXPANDED
                    if state.resolution_status.value == "macro_unexpanded"
                    else MacroExpansionStatus.NOT_APPLICABLE
                ),
                resolution_status=state.resolution_status,
                confidence=confidence,
            )
        )
        owner_component_id = component_ids[state.owner_component_ref]
        edges.append(
            ReactiveEdge(
                id=edge_id_for(
                    owner_component_id=owner_component_id,
                    edge_kind=ReactiveEdgeKind.DECLARES_STATE,
                    source_id=owner_component_id,
                    target_id=state_id,
                    file_path=helper_file.path,
                    line=state.range.start_line,
                ),
                owner_component_id=owner_component_id,
                edge_kind=ReactiveEdgeKind.DECLARES_STATE,
                source_id=owner_component_id,
                target_id=state_id,
                file_path=helper_file.path,
                line=state.range.start_line,
                confidence=confidence,
                resolution_status=state.resolution_status,
            )
        )

    for effect in helper_file.effects:
        component_id = component_ids[effect.owner_component_ref]
        confidence = score_effect_confidence(
            effect_kind=effect.effect_kind,
            resolution_status=effect.resolution_status,
            trigger_expression_kind=effect.trigger_expression_kind,
        )
        effect_id = effect_id_for(
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            language=language,
            component_id=component_id,
            effect_kind=effect.effect_kind,
            file_path=helper_file.path,
            start_line=effect.range.start_line,
            callee_name=effect.callee_name,
        )
        effect_ids[effect.effect_ref] = effect_id
        ref_to_node_id[effect.effect_ref] = effect_id
        effects.append(
            ReactiveEffect(
                id=effect_id,
                group_id=group_id,
                project=project,
                commit_sha=commit_sha,
                language=language,
                component_id=component_id,
                effect_kind=effect.effect_kind,
                callee_name=effect.callee_name,
                file_path=helper_file.path,
                start_line=effect.range.start_line,
                end_line=effect.range.end_line,
                range=effect.range,
                trigger_expression_kind=effect.trigger_expression_kind,
                resolution_status=effect.resolution_status,
                confidence=confidence,
            )
        )

    for edge in helper_file.edges:
        owner_component_id = component_ids[edge.owner_component_ref]
        source_id = state_ids.get(edge.from_ref, effect_ids.get(edge.from_ref))
        target_id = state_ids.get(edge.to_ref, effect_ids.get(edge.to_ref))
        if source_id is None:
            source_id = component_ids[edge.from_ref]
        if target_id is None:
            target_id = component_ids[edge.to_ref]
        confidence = (
            edge.confidence_hint
            if edge.confidence_hint is not None
            else score_edge_confidence(
                edge_kind=edge.edge_kind,
                resolution_status=edge.resolution_status,
                trigger_expression_kind=edge.trigger_expression_kind,
            )
        )
        edges.append(
            ReactiveEdge(
                id=edge_id_for(
                    owner_component_id=owner_component_id,
                    edge_kind=edge.edge_kind,
                    source_id=source_id,
                    target_id=target_id,
                    file_path=helper_file.path,
                    line=edge.range.start_line,
                ),
                owner_component_id=owner_component_id,
                edge_kind=edge.edge_kind,
                source_id=source_id,
                target_id=target_id,
                file_path=helper_file.path,
                line=edge.range.start_line,
                confidence=confidence,
                access_path=edge.access_path,
                binding_kind=edge.binding_kind,
                trigger_expression_kind=edge.trigger_expression_kind,
                resolution_status=edge.resolution_status,
            )
        )

    for diagnostic in helper_file.diagnostics:
        diagnostics.append(
            build_diagnostic(
                group_id=group_id,
                project=project,
                commit_sha=commit_sha,
                run_id=run_id,
                language=language,
                diagnostic_code=diagnostic.code,
                severity=diagnostic.severity,
                file_path=helper_file.path,
                ref=diagnostic.ref,
                message=diagnostic.message,
                range=diagnostic.range,
            )
        )

    return NormalizedReactiveFile(
        file_path=helper_file.path,
        language=language,
        components=tuple(components),
        states=tuple(states),
        effects=tuple(effects),
        edges=tuple(edges),
        diagnostics=tuple(diagnostics),
        ref_to_node_id=ref_to_node_id,
    )
