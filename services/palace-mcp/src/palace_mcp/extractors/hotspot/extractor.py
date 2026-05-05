from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import ClassVar, Literal

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.hotspot import (
    churn_query,
    file_walker,
    lizard_runner,
    neo4j_writer,
)
from palace_mcp.extractors.hotspot.models import ParsedFile


class HotspotExtractor(BaseExtractor):
    name: ClassVar[str] = "hotspot"
    description: ClassVar[str] = (
        "Roadmap #44 — Code Complexity × Churn Hotspot. "
        "Computes Tornhill log-log score per file and writes :Function nodes."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT function_unique IF NOT EXISTS "
        "FOR (fn:Function) REQUIRE (fn.project_id, fn.path, fn.name, fn.start_line) IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX file_hotspot_score IF NOT EXISTS FOR (f:File) ON (f.hotspot_score)",
        "CREATE INDEX function_path IF NOT EXISTS FOR (fn:Function) ON (fn.project_id, fn.path)",
    ]

    async def run(self, *, graphiti: object, ctx: ExtractorRunContext) -> ExtractorStats:  # fmt: skip
        from palace_mcp.mcp_server import get_settings

        settings = get_settings()
        assert settings is not None, "Palace settings not initialised"
        driver = graphiti.driver  # type: ignore[attr-defined]
        run_started_at = datetime.now(tz=timezone.utc)

        files = list(file_walker._walk(ctx.repo_path))

        batch_size: int = settings.palace_hotspot_lizard_batch_size
        timeout_s: int = settings.palace_hotspot_lizard_timeout_s
        behavior: Literal["drop_batch", "fail_run"] = (
            settings.palace_hotspot_lizard_timeout_behavior
        )

        parsed_files: list[ParsedFile] = []
        skipped_paths: list[str] = []
        for i in range(0, max(len(files), 1), batch_size):
            batch = files[i : i + batch_size]
            if not batch:
                continue
            result = await lizard_runner.run_batch(
                batch,
                repo_root=ctx.repo_path,
                timeout_s=timeout_s,
                behavior=behavior,
            )
            parsed_files.extend(result.parsed)
            skipped_paths.extend(result.skipped_files)

        paths = [pf.path for pf in parsed_files]
        preserved_paths = sorted({*paths, *skipped_paths})
        churn_map = await churn_query.fetch_churn(
            driver,
            project_id=ctx.group_id,
            paths=paths,
            window_days=settings.palace_hotspot_churn_window_days,
            run_started_at=run_started_at,
        )

        nodes_w = 0
        edges_w = 0
        for pf in parsed_files:
            await neo4j_writer.write_file_and_functions(
                driver,
                project_id=ctx.group_id,
                parsed_file=pf,
                run_started_at=run_started_at,
            )
            nodes_w += 1 + len(pf.functions)
            edges_w += len(pf.functions)

            churn = churn_map.get(pf.path, 0)
            score = math.log(pf.ccn_total + 1) * math.log(churn + 1)
            await neo4j_writer.write_hotspot_score(
                driver,
                project_id=ctx.group_id,
                path=pf.path,
                churn=churn,
                score=score,
                window_days=settings.palace_hotspot_churn_window_days,
                run_started_at=run_started_at,
            )

        await neo4j_writer.evict_stale_functions(
            driver,
            project_id=ctx.group_id,
            preserved_paths=preserved_paths,
            run_started_at=run_started_at,
        )
        await neo4j_writer.mark_dead_files_zero(
            driver,
            project_id=ctx.group_id,
            preserved_paths=preserved_paths,
            run_started_at=run_started_at,
        )

        return ExtractorStats(nodes_written=nodes_w, edges_written=edges_w)
