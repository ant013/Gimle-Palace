"""Substrate :IngestRun extras writer for cross_repo_version_skew.

Per spec rev2 C8: the extractor does NOT introduce a separate
:OwnershipRun-style label. It writes ownership-style extras onto the
substrate :IngestRun (created by foundation/checkpoint.py).
"""

from __future__ import annotations

from neo4j import AsyncDriver

from palace_mcp.extractors.cross_repo_version_skew.models import RunSummary

_WRITE_EXTRAS_CYPHER = """
MATCH (r:IngestRun {run_id: $run_id})
SET r.mode                            = $mode,
    r.target_slug                     = $target_slug,
    r.member_count                    = $member_count,
    r.target_status_indexed_count     = $target_status_indexed_count,
    r.skew_groups_total               = $skew_groups_total,
    r.skew_groups_major               = $skew_groups_major,
    r.skew_groups_minor               = $skew_groups_minor,
    r.skew_groups_patch               = $skew_groups_patch,
    r.skew_groups_unknown             = $skew_groups_unknown,
    r.aligned_groups_total            = $aligned_groups_total,
    r.warnings_purl_malformed_count   = $warnings_purl_malformed_count
"""


async def _write_run_extras(
    driver: AsyncDriver, *, run_id: str, summary: RunSummary
) -> None:
    """Set ownership-style props on the existing :IngestRun for this run."""
    async with driver.session() as session:
        await session.run(
            _WRITE_EXTRAS_CYPHER,
            run_id=run_id,
            mode=summary.mode,
            target_slug=summary.target_slug,
            member_count=summary.member_count,
            target_status_indexed_count=summary.target_status_indexed_count,
            skew_groups_total=summary.skew_groups_total,
            skew_groups_major=summary.skew_groups_major,
            skew_groups_minor=summary.skew_groups_minor,
            skew_groups_patch=summary.skew_groups_patch,
            skew_groups_unknown=summary.skew_groups_unknown,
            aligned_groups_total=summary.aligned_groups_total,
            warnings_purl_malformed_count=summary.warnings_purl_malformed_count,
        )
