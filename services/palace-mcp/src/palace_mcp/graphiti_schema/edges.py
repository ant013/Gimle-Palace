"""Graphiti edge factory functions for the N+1a edge catalog.

Edge classes are declared here so GIM-77 bridge extractor can import them.
No edge is populated in GIM-75 — heartbeat :Episode has no outgoing edges.
All structural edges (CONTAINS, DEFINES, CALLS, ...) are populated by GIM-77.

Metadata envelope rules: same as entities — confidence + provenance required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from graphiti_core.edges import EntityEdge

_VALID_PROVENANCE = frozenset({"asserted", "derived", "inferred"})


def _validate_envelope(attributes: dict[str, Any]) -> None:
    if "confidence" not in attributes:
        raise ValueError("edge metadata envelope requires 'confidence'")
    if not isinstance(attributes["confidence"], (int, float)):
        raise ValueError("'confidence' must be a number")
    if not (0.0 <= float(attributes["confidence"]) <= 1.0):
        raise ValueError("'confidence' must be in [0, 1]")
    if "provenance" not in attributes:
        raise ValueError("edge metadata envelope requires 'provenance'")
    if attributes["provenance"] not in _VALID_PROVENANCE:
        raise ValueError(
            f"'provenance' must be one of {sorted(_VALID_PROVENANCE)}, "
            f"got {attributes['provenance']!r}"
        )


def _make_edge(
    *,
    group_id: str,
    relation_name: str,
    source_uuid: str,
    target_uuid: str,
    fact: str,
    confidence: float,
    provenance: str,
    extractor: str,
    extractor_version: str,
    observed_at: str | None,
    extra: dict[str, Any] | None,
) -> EntityEdge:
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    created_at = datetime.now(timezone.utc)
    attrs: dict[str, Any] = {
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityEdge(
        group_id=group_id,
        name=relation_name,
        source_node_uuid=source_uuid,
        target_node_uuid=target_uuid,
        fact=fact,
        created_at=created_at,
        attributes=attrs,
    )


# ---------------------------------------------------------------------------
# Structural edges — populated by GIM-77 bridge extractor
# ---------------------------------------------------------------------------


def make_contains(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """Project→Module or Module→File containment."""
    return _make_edge(
        group_id=group_id, relation_name="CONTAINS",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_defines(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """File→Symbol definition."""
    return _make_edge(
        group_id=group_id, relation_name="DEFINES",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_calls(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """Symbol→Symbol call."""
    return _make_edge(
        group_id=group_id, relation_name="CALLS",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_imports(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """File→Module or File→ExternalLib import."""
    return _make_edge(
        group_id=group_id, relation_name="IMPORTS",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_member_of(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """Symbol→ArchitectureCommunity membership."""
    return _make_edge(
        group_id=group_id, relation_name="MEMBER_OF",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_locates_in(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """Hotspot→File location."""
    return _make_edge(
        group_id=group_id, relation_name="LOCATES_IN",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_handles(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    """APIEndpoint→Symbol handler."""
    return _make_edge(
        group_id=group_id, relation_name="HANDLES",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


# ---------------------------------------------------------------------------
# Product/process edges — populated by N+1c+ slices
# ---------------------------------------------------------------------------


def make_concerns(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    return _make_edge(
        group_id=group_id, relation_name="CONCERNS",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_informed_by(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    return _make_edge(
        group_id=group_id, relation_name="INFORMED_BY",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_resolves(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    return _make_edge(
        group_id=group_id, relation_name="RESOLVES",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_touches(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    return _make_edge(
        group_id=group_id, relation_name="TOUCHES",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_modifies(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    return _make_edge(
        group_id=group_id, relation_name="MODIFIES",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )


def make_traced_as(
    *, group_id: str, source_uuid: str, target_uuid: str, fact: str,
    extractor: str, extractor_version: str,
    confidence: float = 1.0, provenance: str = "asserted",
    observed_at: str | None = None, extra: dict[str, Any] | None = None,
) -> EntityEdge:
    return _make_edge(
        group_id=group_id, relation_name="TRACED_AS",
        source_uuid=source_uuid, target_uuid=target_uuid, fact=fact,
        confidence=confidence, provenance=provenance,
        extractor=extractor, extractor_version=extractor_version,
        observed_at=observed_at, extra=extra,
    )
