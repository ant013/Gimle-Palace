"""Cross-repo version skew extractor (Roadmap #39).

4-phase pipeline per spec rev2 §4:
0. bootstrap (resolve targets, validate dependency_surface presence)
1. collect target_status (indexed / not_indexed / not_registered)
2. aggregate via _compute_skew_groups()
3. summary stats + finalize :IngestRun
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.cross_repo_version_skew.compute import (
    _compute_skew_groups,
)
from palace_mcp.extractors.cross_repo_version_skew.models import (
    SLUG_RE,
    RunSummary,
    WarningEntry,
)
from palace_mcp.extractors.cross_repo_version_skew.neo4j_writer import (
    _write_run_extras,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode


class CrossRepoVersionSkewExtractor(BaseExtractor):
    """Roadmap #39 extractor — pure skew detection over GIM-191 :DEPENDS_ON."""

    name: ClassVar[str] = "cross_repo_version_skew"
    description: ClassVar[str] = (
        "Cross-repo version skew detection over :DEPENDS_ON graph"
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        return AuditContract(
            extractor_name="cross_repo_version_skew",
            template_name="cross_repo_version_skew.md",
            query="""
MATCH (p:Project {slug: $project})-[r:DEPENDS_ON]->(d:ExternalDependency)
WITH d.purl AS purl, collect(distinct r.resolved_version) AS versions
WHERE size(versions) > 1
RETURN purl,
       versions,
       size(versions) AS member_count,
       'unknown' AS skew_severity
ORDER BY purl
LIMIT 100
""".strip(),
            severity_column="skew_severity",
            severity_mapper=lambda v: (
                Severity.HIGH
                if v == "major"
                else Severity.MEDIUM
                if v == "minor"
                else Severity.LOW
                if v == "patch"
                else Severity.INFORMATIONAL  # "unknown" and calendar/git-sha versions
            ),
        )

    async def run(
        self,
        *,
        graphiti: Any,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()
        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available — call set_driver() before run_extractor",
                recoverable=False,
                action="retry",
            )

        target_slug = ctx.project_slug
        timeout_s = settings.palace_version_skew_query_timeout_s if settings else 30

        # Auto-detect mode: check if target_slug is a Bundle first
        is_bundle = await self._bundle_exists(driver, target_slug, timeout_s)
        mode = "bundle" if is_bundle else "project"

        try:
            summary, _warnings = await self._pipeline(
                driver=driver,
                mode=mode,
                target_slug=target_slug,
                timeout_s=timeout_s,
                logger=ctx.logger,
            )
            await _write_run_extras(driver, run_id=ctx.run_id, summary=summary)
            return ExtractorStats(nodes_written=1, edges_written=0)
        except ExtractorError as exc:
            if exc.error_code == ExtractorErrorCode.DEPENDENCY_SURFACE_NOT_INDEXED:
                return ExtractorStats(
                    outcome=ExtractorOutcome.MISSING_INPUT,
                    message=exc.message,
                    next_action=(
                        "Run dependency_surface with usable dependency manifests/"
                        "lockfiles if cross_repo_version_skew coverage is required "
                        "for this project."
                    ),
                )
            raise
        except Exception as exc:
            raise ExtractorError(
                error_code=ExtractorErrorCode.EXTRACTOR_RUNTIME_ERROR,
                message=f"unexpected error: {exc}",
                recoverable=False,
                action="manual_cleanup",
            ) from exc

    async def _pipeline(
        self,
        *,
        driver: Any,
        mode: str,
        target_slug: str,
        timeout_s: int,
        logger: Any,
    ) -> tuple[RunSummary, list[WarningEntry]]:
        warnings: list[WarningEntry] = []

        if mode == "project":
            if not SLUG_RE.match(target_slug):
                raise ExtractorError(
                    error_code=ExtractorErrorCode.SLUG_INVALID,
                    message=f"invalid project slug: {target_slug!r}",
                    recoverable=False,
                    action="manual_cleanup",
                )
            members = [target_slug]
            target_status = await self._collect_target_status(
                driver, [target_slug], timeout_s
            )
        else:
            if not SLUG_RE.match(target_slug):
                raise ExtractorError(
                    error_code=ExtractorErrorCode.BUNDLE_INVALID,
                    message=f"invalid bundle slug: {target_slug!r}",
                    recoverable=False,
                    action="manual_cleanup",
                )
            raw_members = await self._bundle_members(driver, target_slug, timeout_s)
            if not raw_members:
                raise ExtractorError(
                    error_code=ExtractorErrorCode.BUNDLE_HAS_NO_MEMBERS,
                    message=f"bundle {target_slug!r} has zero members",
                    recoverable=False,
                    action="manual_cleanup",
                )
            valid_members: list[str] = []
            for slug in raw_members:
                if SLUG_RE.match(slug):
                    valid_members.append(slug)
                else:
                    warnings.append(
                        WarningEntry(
                            code="member_invalid_slug",
                            slug=slug,
                            message=f"member {slug!r} fails slug regex; excluded from query",
                        )
                    )
            members = valid_members
            target_status = await self._collect_target_status(
                driver, members, timeout_s
            )
            for slug, status in target_status.items():
                if status == "not_indexed":
                    warnings.append(
                        WarningEntry(
                            code="member_not_indexed",
                            slug=slug,
                            message=f"{slug} has no :DEPENDS_ON edges; dependency_surface not indexed yet",
                        )
                    )
                elif status == "not_registered":
                    warnings.append(
                        WarningEntry(
                            code="member_not_registered",
                            slug=slug,
                            message=f"{slug} is in :HAS_MEMBER but no :Project node exists",
                        )
                    )

        indexed_count = sum(1 for s in target_status.values() if s == "indexed")
        if indexed_count == 0:
            raise ExtractorError(
                error_code=ExtractorErrorCode.DEPENDENCY_SURFACE_NOT_INDEXED,
                message="all targets lack :DEPENDS_ON data; run dependency_surface first",
                recoverable=False,
                action="manual_cleanup",
            )

        result = await _compute_skew_groups(
            driver,
            mode=mode,  # type: ignore[arg-type]
            member_slugs=members,
            ecosystem=None,
        )
        warnings.extend(result.warnings)

        major = sum(1 for g in result.skew_groups if g.severity == "major")
        minor = sum(1 for g in result.skew_groups if g.severity == "minor")
        patch = sum(1 for g in result.skew_groups if g.severity == "patch")
        unknown = sum(1 for g in result.skew_groups if g.severity == "unknown")
        malformed_count = sum(1 for w in result.warnings if w.code == "purl_malformed")

        summary = RunSummary(
            mode=mode,
            target_slug=target_slug,
            member_count=len(members),
            target_status_indexed_count=indexed_count,
            skew_groups_total=len(result.skew_groups),
            skew_groups_major=major,
            skew_groups_minor=minor,
            skew_groups_patch=patch,
            skew_groups_unknown=unknown,
            aligned_groups_total=result.aligned_groups_total,
            warnings_purl_malformed_count=malformed_count,
        )
        return summary, warnings

    @staticmethod
    async def _bundle_exists(driver: Any, name: str, timeout_s: int) -> bool:
        async with driver.session(default_access_mode="READ") as session:
            result = await session.run(
                "MATCH (b:Bundle {name: $name}) RETURN count(b) AS n",
                name=name,
            )
            row = await result.single()
        return row is not None and row["n"] > 0

    @staticmethod
    async def _bundle_members(driver: Any, bundle: str, timeout_s: int) -> list[str]:
        async with driver.session(default_access_mode="READ") as session:
            result = await session.run(
                """
                MATCH (b:Bundle {name: $name})-[:HAS_MEMBER]->(p:Project)
                RETURN p.slug AS slug
                """,
                name=bundle,
            )
            rows = await result.data()
        return [r["slug"] for r in rows]

    @staticmethod
    async def _collect_target_status(
        driver: Any,
        slugs: list[str],
        timeout_s: int,
    ) -> dict[str, str]:
        """Returns {slug: 'indexed' | 'not_indexed' | 'not_registered'}."""
        async with driver.session(default_access_mode="READ") as session:
            result = await session.run(
                """
                UNWIND $slugs AS slug
                OPTIONAL MATCH (p:Project {slug: slug})
                OPTIONAL MATCH (p)-[r:DEPENDS_ON]->()
                RETURN slug AS s,
                       p IS NOT NULL AS exists,
                       count(r) AS dep_count
                """,
                slugs=slugs,
            )
            rows = await result.data()
        status: dict[str, str] = {}
        for r in rows:
            if not r["exists"]:
                status[r["s"]] = "not_registered"
            elif r["dep_count"] == 0:
                status[r["s"]] = "not_indexed"
            else:
                status[r["s"]] = "indexed"
        return status
