"""Confidence scoring for reactive_dependency_tracer."""

from __future__ import annotations

from palace_mcp.extractors.reactive_dependency_tracer.models import (
    ReactiveConfidence,
    ReactiveEffectKind,
    ReactiveEdgeKind,
    ReactiveResolutionStatus,
    ReactiveStateKind,
    TriggerExpressionKind,
)

_LOW_CONFIDENCE_STATES = frozenset(
    {
        ReactiveStateKind.CALLBACK,
        ReactiveStateKind.DELEGATE,
        ReactiveStateKind.NOTIFICATION,
        ReactiveStateKind.UNKNOWN,
    }
)
_LOW_CONFIDENCE_EFFECTS = frozenset(
    {
        ReactiveEffectKind.CALLBACK,
        ReactiveEffectKind.DELEGATE_CALL,
        ReactiveEffectKind.NETWORK_CALL_CANDIDATE,
        ReactiveEffectKind.STORAGE_WRITE_CANDIDATE,
        ReactiveEffectKind.UNKNOWN,
    }
)
_MEDIUM_ONLY_RESOLUTION = frozenset(
    {
        ReactiveResolutionStatus.SYNTAX_HEURISTIC,
        ReactiveResolutionStatus.SYMBOL_CORRELATED,
        ReactiveResolutionStatus.MACRO_UNEXPANDED,
        ReactiveResolutionStatus.TYPE_UNRESOLVED,
    }
)


def score_state_confidence(
    *,
    state_kind: ReactiveStateKind,
    resolution_status: ReactiveResolutionStatus,
) -> ReactiveConfidence:
    """Score normalized state confidence under the rev3 rules."""

    if state_kind in _LOW_CONFIDENCE_STATES:
        return ReactiveConfidence.LOW
    if resolution_status in _MEDIUM_ONLY_RESOLUTION:
        return ReactiveConfidence.MEDIUM
    return ReactiveConfidence.HIGH


def score_effect_confidence(
    *,
    effect_kind: ReactiveEffectKind,
    resolution_status: ReactiveResolutionStatus,
    trigger_expression_kind: TriggerExpressionKind | None,
) -> ReactiveConfidence:
    """Score normalized effect confidence under the rev3 rules."""

    del trigger_expression_kind
    if effect_kind in _LOW_CONFIDENCE_EFFECTS:
        return ReactiveConfidence.LOW
    if resolution_status in _MEDIUM_ONLY_RESOLUTION:
        return ReactiveConfidence.MEDIUM
    return ReactiveConfidence.HIGH


def score_edge_confidence(
    *,
    edge_kind: ReactiveEdgeKind,
    resolution_status: ReactiveResolutionStatus,
    trigger_expression_kind: TriggerExpressionKind | None,
) -> ReactiveConfidence:
    """Score normalized relationship confidence."""

    if resolution_status in _MEDIUM_ONLY_RESOLUTION:
        return ReactiveConfidence.MEDIUM
    if (
        edge_kind is ReactiveEdgeKind.TRIGGERS_EFFECT
        and trigger_expression_kind is None
    ):
        return ReactiveConfidence.MEDIUM
    return ReactiveConfidence.HIGH
