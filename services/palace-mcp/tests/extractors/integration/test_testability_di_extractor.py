from __future__ import annotations

import logging
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.extractors.testability_di import TestabilityDiExtractor

_FIXTURE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "testability_di" / "mixed_project"
)
PROJECT_SLUG = "wallet"
GROUP_ID = f"project/{PROJECT_SLUG}"


def _make_ctx(repo_path: Path, run_id: str) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=repo_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test.testability_di.integration"),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_integration_writes_all_testability_labels(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    shutil.copytree(_FIXTURE_ROOT, tmp_path, dirs_exist_ok=True)
    await ensure_extractors_schema(driver)

    async with driver.session() as session:
        await session.run(
            """
            CREATE (:Convention {
              project_id: $project_id,
              module: 'WalletKit',
              kind: 'naming.type_class',
              dominant_choice: 'upper_camel',
              confidence: 'heuristic',
              sample_count: 3,
              outliers: 0,
              run_id: 'seed-run'
            })
            """,
            project_id=GROUP_ID,
        )

    stats = await TestabilityDiExtractor().run(
        graphiti=graphiti_mock,
        ctx=_make_ctx(tmp_path, "run-integration-1"),
    )

    assert stats.nodes_written >= 3

    async with driver.session() as session:
        di_count = await session.run(
            "MATCH (n:DiPattern {project_id: $project_id}) RETURN count(n) AS n",
            project_id=GROUP_ID,
        )
        td_count = await session.run(
            "MATCH (n:TestDouble {project_id: $project_id}) RETURN count(n) AS n",
            project_id=GROUP_ID,
        )
        us_count = await session.run(
            "MATCH (n:UntestableSite {project_id: $project_id}) RETURN count(n) AS n",
            project_id=GROUP_ID,
        )
        convention_count = await session.run(
            "MATCH (n:Convention {project_id: $project_id}) RETURN count(n) AS n",
            project_id=GROUP_ID,
        )

        di_row = await di_count.single()
        td_row = await td_count.single()
        us_row = await us_count.single()
        convention_row = await convention_count.single()

    assert di_row is not None and di_row["n"] >= 1
    assert td_row is not None and td_row["n"] >= 1
    assert us_row is not None and us_row["n"] >= 1
    assert convention_row is not None and convention_row["n"] == 1
