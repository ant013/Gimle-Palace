"""Extractor shell for soft-deprecating stale Swift symbols."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, ClassVar

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorRuntimeError,
    ExtractorStats,
)
from palace_mcp.extractors.prune_swift_symbols.cypher import (
    APPLY_DEPRECATION_BATCH,
    CREATE_DEPRECATION_EVENT,
    PRECHECK_STALE,
)
from palace_mcp.extractors.prune_swift_symbols.subprocess_helpers import (
    get_git_head_sha,
)

DEFAULT_THRESHOLD_RATIO = 0.5
APPLY_BATCH_SIZE = 5000


@dataclass(frozen=True)
class ApplyResult:
    event_id: str
    deprecated_count: int
    deprecated_files: int
    deprecated_symbols: int


async def _precheck_stale(
    driver: Any,
    *,
    project_id: str,
    companion_run_id: str,
) -> tuple[int, int]:
    result = await driver.execute_query(
        PRECHECK_STALE,
        project_id=project_id,
        companion_run_id=companion_run_id,
    )
    if not result.records:
        return 0, 0
    row = result.records[0]
    return int(row["stale_total"]), int(row["overall_total"])


async def _apply_deprecation(
    driver: Any,
    *,
    project_id: str,
    companion_run_id: str,
    head_sha: str,
    run_id: str,
    threshold_ratio_effective: float,
) -> ApplyResult:
    total_deprecated = 0
    total_files = 0
    total_symbols = 0

    while True:
        batch = await driver.execute_query(
            APPLY_DEPRECATION_BATCH,
            project_id=project_id,
            companion_run_id=companion_run_id,
            head_sha=head_sha,
            batch_size=APPLY_BATCH_SIZE,
        )
        row = batch.records[0]
        batch_count = int(row["batch_count"])
        if batch_count == 0:
            break
        total_deprecated += batch_count
        total_files += int(row["batch_files"])
        total_symbols += int(row["batch_symbols"])
        if batch_count < APPLY_BATCH_SIZE:
            break

    event = await driver.execute_query(
        CREATE_DEPRECATION_EVENT,
        project_id=project_id,
        run_id=run_id,
        companion_run_id=companion_run_id,
        head_sha=head_sha,
        total_deprecated=total_deprecated,
        total_files=total_files,
        total_symbols=total_symbols,
        threshold_ratio_effective=threshold_ratio_effective,
    )
    event_id = event.records[0]["event_id"] if event.records else ""
    return ApplyResult(
        event_id=event_id,
        deprecated_count=total_deprecated,
        deprecated_files=total_files,
        deprecated_symbols=total_symbols,
    )


class PruneSwiftSymbols(BaseExtractor):
    """Soft-delete stale :File/:Symbol nodes after a companion Swift index run."""

    name: ClassVar[str] = "prune_swift_symbols"
    description: ClassVar[str] = (
        "Marks stale Swift :File and :Symbol nodes as :Deprecated after a "
        "successful companion symbol_index_swift run."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []
    timeout_s: ClassVar[float] = 600.0

    async def run(self, *, graphiti: Any, ctx: ExtractorRunContext) -> ExtractorStats:
        companion_run_id = ctx.companion_run_id
        if not companion_run_id:
            return ExtractorStats(
                outcome=ExtractorOutcome.SKIPPED,
                message="no companion run_id provided; skipping prune",
                next_action=(
                    "Run symbol_index_swift first so prune_swift_symbols receives "
                    "a companion run_id."
                ),
            )

        try:
            head_sha = get_git_head_sha(ctx.repo_path)
        except subprocess.CalledProcessError as exc:
            raise ExtractorRuntimeError(
                f"git rev-parse HEAD failed in {ctx.repo_path}: {exc}"
            ) from exc

        driver = graphiti.driver
        stale_total, overall_total = await _precheck_stale(
            driver,
            project_id=ctx.group_id,
            companion_run_id=companion_run_id,
        )
        ratio = stale_total / overall_total if overall_total else 0.0
        if overall_total and ratio > DEFAULT_THRESHOLD_RATIO:
            return ExtractorStats(
                outcome=ExtractorOutcome.SKIPPED,
                message=(
                    f"would deprecate {stale_total}/{overall_total} "
                    f"({ratio * 100:.1f}%) > threshold "
                    f"{DEFAULT_THRESHOLD_RATIO * 100:.0f}%"
                ),
                next_action=(
                    "Reduce stale nodes before enabling prune, or explicitly "
                    "override the threshold in a later slice."
                ),
            )

        result = await _apply_deprecation(
            driver,
            project_id=ctx.group_id,
            companion_run_id=companion_run_id,
            head_sha=head_sha,
            run_id=ctx.run_id,
            threshold_ratio_effective=DEFAULT_THRESHOLD_RATIO,
        )
        return ExtractorStats(
            nodes_written=result.deprecated_count,
            message=(
                f"deprecated {result.deprecated_count} stale nodes "
                f"(files={result.deprecated_files}, symbols={result.deprecated_symbols})"
            ),
        )
