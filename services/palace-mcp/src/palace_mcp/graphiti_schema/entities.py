"""Graphiti entity factory functions for the N+1a entity catalog.

Each factory constructs an EntityNode with the correct labels and validates
the required metadata envelope (confidence + provenance). Entity-specific
attrs are merged on top.

Entities populated in GIM-75 (heartbeat slice): Episode.
All others are declared so GIM-77 bridge extractor can import and write them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from graphiti_core.nodes import EntityNode

# ---------------------------------------------------------------------------
# Metadata envelope validation
# ---------------------------------------------------------------------------

_VALID_PROVENANCE = frozenset({"asserted", "derived", "inferred"})
_VALID_SYMBOL_KINDS = frozenset({"function", "method", "class", "interface", "enum", "type"})


def _validate_envelope(attributes: dict[str, Any]) -> None:
    """Raise ValueError if required metadata envelope fields are missing/invalid."""
    if "confidence" not in attributes:
        raise ValueError("metadata envelope requires 'confidence'")
    if not isinstance(attributes["confidence"], (int, float)):
        raise ValueError("'confidence' must be a number")
    if not (0.0 <= float(attributes["confidence"]) <= 1.0):
        raise ValueError("'confidence' must be in [0, 1]")
    if "provenance" not in attributes:
        raise ValueError("metadata envelope requires 'provenance'")
    if attributes["provenance"] not in _VALID_PROVENANCE:
        raise ValueError(
            f"'provenance' must be one of {sorted(_VALID_PROVENANCE)}, "
            f"got {attributes['provenance']!r}"
        )


# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------


def make_episode(
    *,
    group_id: str,
    name: str,
    kind: str,
    source: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Episode nodes (heartbeat ticks, git pushes, extractor runs)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "kind": kind,
        "source": source,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["Episode"], attributes=attrs)


def make_project(
    *,
    group_id: str,
    slug: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Project nodes."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "slug": slug,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=slug, group_id=group_id, labels=["Project"], attributes=attrs)


def make_iteration(
    *,
    group_id: str,
    name: str,
    number: int,
    kind: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Iteration nodes (ingest runs / milestones)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "number": number,
        "kind": kind,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["Iteration"], attributes=attrs)


def make_decision(
    *,
    group_id: str,
    name: str,
    text: str,
    status: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Decision nodes (ADR-style architectural decisions)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "text": text,
        "status": status,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["Decision"], attributes=attrs)


def make_iteration_note(
    *,
    group_id: str,
    name: str,
    iteration_ref: str,
    text: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :IterationNote nodes."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "iteration_ref": iteration_ref,
        "text": text,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["IterationNote"], attributes=attrs)


def make_finding(
    *,
    group_id: str,
    name: str,
    severity: str,
    category: str,
    text: str,
    source: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Finding nodes (reviewer-produced findings)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "severity": severity,
        "category": category,
        "text": text,
        "source": source,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["Finding"], attributes=attrs)


def make_module(
    *,
    group_id: str,
    name: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Module nodes (projected by GIM-77 bridge)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
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
    return EntityNode(name=name, group_id=group_id, labels=["Module"], attributes=attrs)


def make_file(
    *,
    group_id: str,
    path: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :File nodes (projected by GIM-77 bridge)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "path": path,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=path, group_id=group_id, labels=["File"], attributes=attrs)


def make_symbol(
    *,
    group_id: str,
    name: str,
    kind: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Symbol nodes. kind must be one of the declared enum values."""
    if kind not in _VALID_SYMBOL_KINDS:
        raise ValueError(
            f"Symbol kind must be one of {sorted(_VALID_SYMBOL_KINDS)}, got {kind!r}"
        )
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["Symbol"], attributes=attrs)


def make_api_endpoint(
    *,
    group_id: str,
    name: str,
    method: str,
    path: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :APIEndpoint nodes."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "method": method,
        "path": path,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["APIEndpoint"], attributes=attrs)


def make_model(
    *,
    group_id: str,
    name: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Model nodes (domain data-model entity)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
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
    return EntityNode(name=name, group_id=group_id, labels=["Model"], attributes=attrs)


def make_repository(
    *,
    group_id: str,
    name: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Repository nodes (data-access layer entity)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
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
    return EntityNode(name=name, group_id=group_id, labels=["Repository"], attributes=attrs)


def make_external_lib(
    *,
    group_id: str,
    name: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :ExternalLib nodes (third-party dependency)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
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
    return EntityNode(name=name, group_id=group_id, labels=["ExternalLib"], attributes=attrs)


def make_trace(
    *,
    group_id: str,
    name: str,
    agent_id: str,
    confidence: float = 1.0,
    provenance: str = "asserted",
    extractor: str,
    extractor_version: str,
    observed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EntityNode:
    """Factory for :Trace nodes (Paperclip-agent reasoning chains)."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    attrs: dict[str, Any] = {
        "agent_id": agent_id,
        "confidence": confidence,
        "provenance": provenance,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "evidence_ref": [],
        "observed_at": observed_at,
        **(extra or {}),
    }
    _validate_envelope(attrs)
    return EntityNode(name=name, group_id=group_id, labels=["Trace"], attributes=attrs)
