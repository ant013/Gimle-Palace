"""Extractor registry — module-level dict of registered extractors.

Production registration is import-time (EXTRACTORS dict literal). Runtime
register() is test-only (for fixtures). Single-event-loop semantics mean
no thread-safety needed.
"""

from __future__ import annotations

from palace_mcp.extractors.base import BaseExtractor
from palace_mcp.extractors.codebase_memory_bridge import CodebaseMemoryBridgeExtractor
from palace_mcp.extractors.heartbeat import HeartbeatExtractor

EXTRACTORS: dict[str, BaseExtractor] = {
    "heartbeat": HeartbeatExtractor(),
    "codebase_memory_bridge": CodebaseMemoryBridgeExtractor(),
}


def register(extractor: BaseExtractor) -> None:
    """Add an extractor to the registry.

    Production use: module-level (import-time). Test use: in fixture.
    Raises ValueError if name already registered.
    """
    if extractor.name in EXTRACTORS:
        raise ValueError(f"extractor already registered: {extractor.name!r}")
    EXTRACTORS[extractor.name] = extractor


def get(name: str) -> BaseExtractor | None:
    """Look up extractor by name. Returns None if not registered."""
    return EXTRACTORS.get(name)


def list_all() -> list[BaseExtractor]:
    """All registered extractors, in insertion order."""
    return list(EXTRACTORS.values())
