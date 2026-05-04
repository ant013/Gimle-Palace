"""DependencySurfaceExtractor — orchestrates SPM, Gradle, Python sub-parsers.

Single-phase: parse manifests → write :ExternalDependency + :DEPENDS_ON edges.
No Tantivy, no checkpoint state (full re-parse is fine for tens-to-thousands of deps).
"""

from __future__ import annotations

import logging
from typing import ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.dependency_surface.models import ParsedDep
from palace_mcp.extractors.dependency_surface.neo4j_writer import write_to_neo4j
from palace_mcp.extractors.dependency_surface.parsers.gradle import parse_gradle
from palace_mcp.extractors.dependency_surface.parsers.python import parse_python
from palace_mcp.extractors.dependency_surface.parsers.spm import parse_spm
from palace_mcp.extractors.foundation.schema import ensure_custom_schema

logger = logging.getLogger(__name__)


class DependencySurfaceExtractor(BaseExtractor):
    name: ClassVar[str] = "dependency_surface"
    description: ClassVar[str] = (
        "Parse declared + resolved dependencies from SPM, Gradle, Python manifests "
        "and write :ExternalDependency nodes + :DEPENDS_ON edges."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        # Deferred import to avoid circular import (mcp_server → registry → here → mcp_server)
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            from palace_mcp.extractors.foundation.errors import (
                ExtractorError,
                ExtractorErrorCode,
            )

            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available",
                recoverable=False,
                action="retry",
            )

        await ensure_custom_schema(driver)

        all_deps: list[ParsedDep] = []
        ecosystems_present: list[str] = []
        parse_failures: list[str] = []

        repo_path = ctx.repo_path
        project_id = ctx.group_id

        # SPM
        try:
            spm_result = parse_spm(repo_path, project_id=project_id)
            if spm_result.deps:
                all_deps.extend(spm_result.deps)
                ecosystems_present.append("github")
            for w in spm_result.parser_warnings:
                ctx.logger.warning("dep_surface_spm_warning: %s", w)
        except Exception as exc:
            parse_failures.append("github")
            ctx.logger.error("dep_surface_failed ecosystem=github error=%r", exc)

        # Gradle
        try:
            gradle_result = parse_gradle(repo_path, project_id=project_id)
            if gradle_result.deps:
                all_deps.extend(gradle_result.deps)
                ecosystems_present.append("maven")
            for w in gradle_result.parser_warnings:
                ctx.logger.warning("dep_surface_gradle_warning: %s", w)
        except Exception as exc:
            parse_failures.append("maven")
            ctx.logger.error("dep_surface_failed ecosystem=maven error=%r", exc)

        # Python
        try:
            python_result = parse_python(repo_path, project_id=project_id)
            if python_result.deps:
                all_deps.extend(python_result.deps)
                ecosystems_present.append("pypi")
            for w in python_result.parser_warnings:
                ctx.logger.warning("dep_surface_python_warning: %s", w)
        except Exception as exc:
            parse_failures.append("pypi")
            ctx.logger.error("dep_surface_failed ecosystem=pypi error=%r", exc)

        if not all_deps:
            ctx.logger.warning(
                "dep_surface_no_manifests project=%s repo_path=%s",
                ctx.project_slug,
                repo_path,
            )
            return ExtractorStats(nodes_written=0, edges_written=0)

        nodes_created, edges_created = await write_to_neo4j(
            driver,
            all_deps,
            project_slug=ctx.project_slug,
            group_id=ctx.group_id,
        )

        ctx.logger.info(
            "dep_surface_complete project=%s nodes=%d edges=%d ecosystems=%s failures=%s",
            ctx.project_slug,
            nodes_created,
            edges_created,
            ecosystems_present,
            parse_failures or "none",
        )

        return ExtractorStats(nodes_written=nodes_created, edges_written=edges_created)
