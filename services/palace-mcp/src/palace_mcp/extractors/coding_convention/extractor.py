"""Coding convention extractor scaffolding (Roadmap #6)."""

from __future__ import annotations

from typing import ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)


class CodingConventionExtractor(BaseExtractor):
    """Scaffold for project-specific coding convention extraction."""

    name: ClassVar[str] = "coding_convention"
    description: ClassVar[str] = (
        "Detect dominant Swift and Kotlin coding conventions together with outliers."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX convention_lookup IF NOT EXISTS "
        "FOR (c:Convention) ON (c.project_id, c.module, c.kind)",
        "CREATE INDEX convention_violation_severity IF NOT EXISTS "
        "FOR (v:ConventionViolation) ON (v.project_id, v.severity)",
    ]

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti, ctx
        return ExtractorStats()
