"""Stable identifiers for reactive_dependency_tracer."""

from __future__ import annotations

import hashlib

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    Range,
    ReactiveComponentKind,
    ReactiveDiagnosticCode,
    ReactiveEffectKind,
    ReactiveEdgeKind,
    ReactiveStateKind,
)


def _stable_id(*parts: str) -> str:
    payload = "||".join(parts)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def component_id_for(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    language: Language,
    component_kind: ReactiveComponentKind,
    qualified_name: str,
    file_path: str,
    start_line: int,
) -> str:
    return _stable_id(
        group_id,
        project,
        commit_sha,
        language.value,
        component_kind.value,
        qualified_name,
        file_path,
        str(start_line),
    )


def state_id_for(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    language: Language,
    owner_qualified_name: str,
    state_name: str,
    state_kind: ReactiveStateKind,
    file_path: str,
) -> str:
    return _stable_id(
        group_id,
        project,
        commit_sha,
        language.value,
        owner_qualified_name,
        state_name,
        state_kind.value,
        file_path,
    )


def effect_id_for(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    language: Language,
    component_id: str,
    effect_kind: ReactiveEffectKind,
    file_path: str,
    start_line: int,
    callee_name: str | None,
) -> str:
    return _stable_id(
        group_id,
        project,
        commit_sha,
        language.value,
        component_id,
        effect_kind.value,
        file_path,
        str(start_line),
        callee_name or "",
    )


def diagnostic_id_for(
    *,
    group_id: str,
    project: str,
    commit_sha: str,
    diagnostic_code: ReactiveDiagnosticCode,
    file_path: str | None,
    ref: str | None,
    range: Range | None,
) -> str:
    range_key = ""
    if range is not None:
        range_key = (
            f"{range.start_line}:{range.start_col}:{range.end_line}:{range.end_col}"
        )
    return _stable_id(
        group_id,
        project,
        commit_sha,
        diagnostic_code.value,
        file_path or "",
        ref or "",
        range_key,
    )


def edge_id_for(
    *,
    owner_component_id: str,
    edge_kind: ReactiveEdgeKind,
    source_id: str,
    target_id: str,
    file_path: str,
    line: int,
) -> str:
    return _stable_id(
        owner_component_id,
        edge_kind.value,
        source_id,
        target_id,
        file_path,
        str(line),
    )
