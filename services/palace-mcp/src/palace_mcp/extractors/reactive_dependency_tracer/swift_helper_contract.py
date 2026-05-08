"""Swift helper JSON contract parser for reactive_dependency_tracer."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from palace_mcp.extractors.reactive_dependency_tracer.models import (
    DiagnosticSeverity,
    Range,
    ReactiveComponentKind,
    ReactiveConfidence,
    ReactiveDiagnosticCode,
    ReactiveEdgeKind,
    ReactiveEffectKind,
    ReactiveResolutionStatus,
    ReactiveStateKind,
    TriggerExpressionKind,
)

MAX_SWIFT_HELPER_JSON_BYTES = 1_000_000
MAX_FILES_PER_RUN = 128
MAX_WARNINGS_PER_FILE = 64
MAX_EDGES_PER_FILE = 512
SUPPORTED_SCHEMA_VERSION = 1


class SwiftHelperDiagnostic(BaseModel):
    """One helper-emitted warning or skip record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ReactiveDiagnosticCode
    severity: DiagnosticSeverity
    ref: str | None = None
    message: str | None = None
    range: Range | None = None


class SwiftHelperComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    component_ref: str
    module_name: str
    component_kind: ReactiveComponentKind
    qualified_name: str
    display_name: str
    range: Range
    resolution_status: ReactiveResolutionStatus


class SwiftHelperState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state_ref: str
    owner_component_ref: str
    module_name: str
    state_name: str
    state_kind: ReactiveStateKind
    wrapper_or_api: str | None = None
    declared_type: str | None = None
    range: Range
    resolution_status: ReactiveResolutionStatus


class SwiftHelperEffect(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effect_ref: str
    owner_component_ref: str
    effect_kind: ReactiveEffectKind
    callee_name: str | None = None
    trigger_expression_kind: TriggerExpressionKind | None = None
    range: Range
    resolution_status: ReactiveResolutionStatus


class SwiftHelperEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_ref: str
    edge_kind: ReactiveEdgeKind
    from_ref: str
    to_ref: str
    owner_component_ref: str
    access_path: str | None = None
    binding_kind: str | None = None
    trigger_expression_kind: TriggerExpressionKind | None = None
    range: Range
    confidence_hint: ReactiveConfidence | None = None
    resolution_status: ReactiveResolutionStatus

    @model_validator(mode="after")
    def _validate_trigger_contract(self) -> "SwiftHelperEdge":
        if (
            self.edge_kind is ReactiveEdgeKind.TRIGGERS_EFFECT
            and self.trigger_expression_kind is None
        ):
            raise ValueError(
                "trigger_expression_kind is required for triggers_effect edges"
            )
        return self


class SwiftHelperFile(BaseModel):
    """One parsed Swift source file emitted by the helper."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    module_name: str
    parse_status: str
    components: tuple[SwiftHelperComponent, ...] = ()
    states: tuple[SwiftHelperState, ...] = ()
    effects: tuple[SwiftHelperEffect, ...] = ()
    edges: tuple[SwiftHelperEdge, ...] = ()
    diagnostics: tuple[SwiftHelperDiagnostic, ...] = ()

    @model_validator(mode="after")
    def _validate_ref_integrity(self) -> "SwiftHelperFile":
        if len(self.diagnostics) > MAX_WARNINGS_PER_FILE:
            raise ValueError("max warnings per file exceeded")
        if len(self.edges) > MAX_EDGES_PER_FILE:
            raise ValueError("max edges per file exceeded")

        all_refs: set[str] = set()
        component_refs = {component.component_ref for component in self.components}
        for ref in component_refs:
            if ref in all_refs:
                raise ValueError(f"duplicate ref detected: {ref}")
            all_refs.add(ref)

        state_refs = {state.state_ref for state in self.states}
        for ref in state_refs:
            if ref in all_refs:
                raise ValueError(f"duplicate ref detected: {ref}")
            all_refs.add(ref)

        effect_refs = {effect.effect_ref for effect in self.effects}
        for ref in effect_refs:
            if ref in all_refs:
                raise ValueError(f"duplicate ref detected: {ref}")
            all_refs.add(ref)

        for edge in self.edges:
            if edge.edge_ref in all_refs:
                raise ValueError(f"duplicate ref detected: {edge.edge_ref}")
            all_refs.add(edge.edge_ref)

        if len(component_refs) != len(self.components):
            raise ValueError("duplicate component_ref detected")
        if len(state_refs) != len(self.states):
            raise ValueError("duplicate state_ref detected")
        if len(effect_refs) != len(self.effects):
            raise ValueError("duplicate effect_ref detected")

        for state in self.states:
            if state.owner_component_ref not in component_refs:
                raise ValueError(
                    f"dangling owner_component_ref: {state.owner_component_ref}"
                )
        for effect in self.effects:
            if effect.owner_component_ref not in component_refs:
                raise ValueError(
                    f"dangling owner_component_ref: {effect.owner_component_ref}"
                )

        known_entity_refs = component_refs | state_refs | effect_refs
        for edge in self.edges:
            if edge.owner_component_ref not in component_refs:
                raise ValueError(
                    f"dangling owner_component_ref: {edge.owner_component_ref}"
                )
            if (
                edge.from_ref not in known_entity_refs
                or edge.to_ref not in known_entity_refs
            ):
                raise ValueError("dangling edge ref detected")
        for diagnostic in self.diagnostics:
            if diagnostic.ref is not None and diagnostic.ref not in all_refs:
                raise ValueError(f"invalid helper ref: {diagnostic.ref}")
        return self


class SwiftHelperDocument(BaseModel):
    """Top-level helper document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str
    tool_version: str
    schema_version: int
    swift_syntax_version: str
    swift_toolchain: str
    files: tuple[SwiftHelperFile, ...]
    run_diagnostics: tuple[SwiftHelperDiagnostic, ...] = ()

    @model_validator(mode="after")
    def _validate_top_level_bounds(self) -> "SwiftHelperDocument":
        if self.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ValueError(f"schema_version {self.schema_version} is unsupported")
        if len(self.files) > MAX_FILES_PER_RUN:
            raise ValueError("max files per run exceeded")
        return self


def _validate_repo_relative_path(path_value: str, repo_root: Path) -> str:
    stripped = path_value.strip()
    if not stripped:
        raise ValueError("path_empty")
    if "\\" in stripped:
        raise ValueError("path_windows_separator")
    if stripped.startswith("~"):
        raise ValueError("path_absolute_outside_repo")

    posix_path = PurePosixPath(stripped)
    if posix_path.is_absolute():
        raise ValueError("path_absolute_outside_repo")
    if any(part == ".." for part in posix_path.parts):
        raise ValueError("path_parent_traversal")

    candidate = repo_root / Path(posix_path.as_posix())
    if candidate.exists() and candidate.is_symlink():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError as exc:  # pragma: no cover - FS-dependent safeguard
            raise ValueError("path_symlink_escape") from exc
    return posix_path.as_posix()


def parse_swift_helper_contract(
    payload: str, *, repo_root: Path
) -> SwiftHelperDocument:
    """Parse + validate an untrusted helper JSON document."""

    payload_bytes = payload.encode("utf-8")
    if len(payload_bytes) > MAX_SWIFT_HELPER_JSON_BYTES:
        raise ValueError("helper_json_too_large")

    try:
        raw = json.loads(payload)
        document = SwiftHelperDocument.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(str(exc)) from exc

    normalized_files: list[SwiftHelperFile] = []
    for helper_file in document.files:
        normalized_path = _validate_repo_relative_path(helper_file.path, repo_root)
        normalized_files.append(
            helper_file.model_copy(update={"path": normalized_path})
        )

    return document.model_copy(update={"files": tuple(normalized_files)})
