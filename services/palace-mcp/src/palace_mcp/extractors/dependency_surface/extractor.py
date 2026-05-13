"""DependencySurfaceExtractor — orchestrates SPM, Gradle, Python sub-parsers.

Single-phase: parse manifests → write :ExternalDependency + :DEPENDS_ON edges.
No Tantivy, no checkpoint state (full re-parse is fine for tens-to-thousands of deps).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

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

# Directories to prune during manifest discovery (relative path segments).
_STOP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "node_modules", "target", "dist", "build", "__pycache__"}
)
# Relative path fragment that excludes test fixtures from production ingest.
_FIXTURE_STOP = "tests/extractors/fixtures"


def _walk(root: Path, name: str) -> Iterator[Path]:
    """Yield files matching name under root, skipping pruned directories.

    All checks use the path relative to root so fixture directories that happen
    to be the repo_path itself are not erroneously excluded.
    """
    for p in root.rglob(name):
        rel = p.relative_to(root)
        if (
            any(seg in _STOP_DIRS for seg in rel.parts)
            or _FIXTURE_STOP in rel.as_posix()
        ):
            continue
        yield p


class DependencySurfaceExtractor(BaseExtractor):
    name: ClassVar[str] = "dependency_surface"
    description: ClassVar[str] = (
        "Parse declared + resolved dependencies from SPM, Gradle, Python manifests "
        "and write :ExternalDependency nodes + :DEPENDS_ON edges."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        return AuditContract(
            extractor_name="dependency_surface",
            template_name="dependency_surface.md",
            query="""
MATCH (p:Project {slug: $project})-[r:DEPENDS_ON]->(d:ExternalDependency)
RETURN d.purl AS purl,
       r.scope AS scope,
       r.declared_in AS declared_in,
       r.declared_version_constraint AS declared_version_constraint,
       r.resolved_version AS resolved_version
ORDER BY d.purl
LIMIT 100
""".strip(),
            severity_column="purl",
            # Dependency listings are informational — severity lives in cross_repo_version_skew
            severity_mapper=lambda v: Severity.INFORMATIONAL,
        )

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

        repo_path = ctx.repo_path
        project_id = ctx.group_id

        # Discover manifests via rglob with stop-list.
        # Manifests are NOT guaranteed to be at repo root (e.g. gimle has
        # services/palace-mcp/pyproject.toml, services/watchdog/pyproject.toml).
        spm_files = list(_walk(repo_path, "Package.swift"))
        gradle_libs = list(_walk(repo_path, "libs.versions.toml"))
        gradle_modules = list(_walk(repo_path, "build.gradle.kts"))
        python_pyprojects = list(_walk(repo_path, "pyproject.toml"))

        gradle_present = bool(gradle_libs or gradle_modules)
        if not (spm_files or gradle_present or python_pyprojects):
            ctx.logger.warning(
                "dep_surface_no_manifests project=%s repo_path=%s",
                ctx.project_slug,
                repo_path,
            )
            return ExtractorStats(nodes_written=0, edges_written=0)

        all_deps: list[ParsedDep] = []
        ecosystems_present: list[str] = []
        parse_failures: list[str] = []

        # SPM: one parse per Package.swift directory (supports multi-package repos).
        for spm_root in sorted({p.parent for p in spm_files}):
            try:
                spm_result = parse_spm(spm_root, project_id=project_id)
                if spm_result.deps:
                    all_deps.extend(spm_result.deps)
                    if "github" not in ecosystems_present:
                        ecosystems_present.append("github")
                for w in spm_result.parser_warnings:
                    ctx.logger.warning("dep_surface_spm_warning: %s", w)
            except Exception as exc:
                if "github" not in parse_failures:
                    parse_failures.append("github")
                ctx.logger.error("dep_surface_failed ecosystem=github error=%r", exc)

        # Gradle: single pass; discovered catalog + module files passed explicitly
        # so the stop-list applied during discovery takes effect.
        if gradle_present:
            try:
                gradle_result = parse_gradle(
                    repo_path,
                    project_id=project_id,
                    libs_files=gradle_libs,
                    kts_files=gradle_modules,
                )
                if gradle_result.deps:
                    all_deps.extend(gradle_result.deps)
                    ecosystems_present.append("maven")
                for w in gradle_result.parser_warnings:
                    ctx.logger.warning("dep_surface_gradle_warning: %s", w)
            except Exception as exc:
                parse_failures.append("maven")
                ctx.logger.error("dep_surface_failed ecosystem=maven error=%r", exc)

        # Python: one parse per pyproject.toml directory (supports multi-package repos
        # like gimle which has services/palace-mcp/pyproject.toml AND
        # services/watchdog/pyproject.toml).
        for py_root in sorted({p.parent for p in python_pyprojects}):
            try:
                python_result = parse_python(py_root, project_id=project_id)
                if python_result.deps:
                    all_deps.extend(python_result.deps)
                    if "pypi" not in ecosystems_present:
                        ecosystems_present.append("pypi")
                for w in python_result.parser_warnings:
                    ctx.logger.warning("dep_surface_python_warning: %s", w)
            except Exception as exc:
                if "pypi" not in parse_failures:
                    parse_failures.append("pypi")
                ctx.logger.error("dep_surface_failed ecosystem=pypi error=%r", exc)

        if not all_deps:
            ctx.logger.info(
                "dep_surface_no_deps project=%s ecosystems_checked=%s",
                ctx.project_slug,
                ecosystems_present or ["none"],
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
