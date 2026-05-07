"""Unit tests for reactive_dependency_tracer confidence scoring."""

from __future__ import annotations

from palace_mcp.extractors.reactive_dependency_tracer.confidence import (
    score_effect_confidence,
    score_edge_confidence,
    score_state_confidence,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    ReactiveConfidence,
    ReactiveEffectKind,
    ReactiveEdgeKind,
    ReactiveResolutionStatus,
    ReactiveStateKind,
    TriggerExpressionKind,
)


def test_exact_state_is_high_confidence() -> None:
    assert (
        score_state_confidence(
            state_kind=ReactiveStateKind.STATE,
            resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        )
        is ReactiveConfidence.HIGH
    )


def test_dynamic_state_is_low_confidence() -> None:
    assert (
        score_state_confidence(
            state_kind=ReactiveStateKind.DELEGATE,
            resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        )
        is ReactiveConfidence.LOW
    )


def test_symbol_correlated_state_is_medium_confidence() -> None:
    assert (
        score_state_confidence(
            state_kind=ReactiveStateKind.OBSERVABLE_OBJECT,
            resolution_status=ReactiveResolutionStatus.SYMBOL_CORRELATED,
        )
        is ReactiveConfidence.MEDIUM
    )


def test_unresolved_effect_cannot_be_high() -> None:
    assert (
        score_effect_confidence(
            effect_kind=ReactiveEffectKind.ON_CHANGE,
            resolution_status=ReactiveResolutionStatus.TYPE_UNRESOLVED,
            trigger_expression_kind=TriggerExpressionKind.ON_CHANGE_OF,
        )
        is ReactiveConfidence.MEDIUM
    )


def test_delegate_effect_is_low_confidence() -> None:
    assert (
        score_effect_confidence(
            effect_kind=ReactiveEffectKind.DELEGATE_CALL,
            resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
            trigger_expression_kind=None,
        )
        is ReactiveConfidence.LOW
    )


def test_explicit_trigger_edge_uses_high_confidence() -> None:
    assert (
        score_edge_confidence(
            edge_kind=ReactiveEdgeKind.TRIGGERS_EFFECT,
            resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
            trigger_expression_kind=TriggerExpressionKind.ON_CHANGE_OF,
        )
        is ReactiveConfidence.HIGH
    )


def test_heuristic_edge_downgrades_to_medium() -> None:
    assert (
        score_edge_confidence(
            edge_kind=ReactiveEdgeKind.READS_STATE,
            resolution_status=ReactiveResolutionStatus.SYNTAX_HEURISTIC,
            trigger_expression_kind=None,
        )
        is ReactiveConfidence.MEDIUM
    )
