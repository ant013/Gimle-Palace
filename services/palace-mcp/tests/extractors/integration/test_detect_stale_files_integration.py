from __future__ import annotations

import hashlib
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest
from neo4j import AsyncDriver

from palace_mcp.memory.schema import ProjectInfo
from palace_mcp.ops.detect_stale_files import detect_project_stale_files


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_project_stale_files_reads_latest_ingest_run_and_file_hashes(
    driver: AsyncDriver,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repos"
    repo_path = repo_root / "TronKit.Swift"
    swift_file = repo_path / "Sources" / "Wallet.swift"
    swift_file.parent.mkdir(parents=True)
    swift_file.write_text("struct Wallet { let id: Int }\n", encoding="utf-8")

    previous_finished_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    current_body_hash = hashlib.sha256(swift_file.read_bytes()).hexdigest()

    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $slug,
                p.tags = [],
                p.relative_path = $relative_path,
                p.language_profile = 'swift_kit'
            """,
            slug="tron-kit",
            relative_path="TronKit.Swift",
        )
        await session.run(
            """
            CREATE (r:IngestRun {
                run_id: 'run-1',
                project: $slug,
                extractor_name: 'symbol_index_swift',
                started_at: datetime($started_at),
                finished_at: datetime($finished_at)
            })
            """,
            slug="tron-kit",
            started_at=(previous_finished_at - timedelta(seconds=5)).isoformat(),
            finished_at=previous_finished_at.isoformat(),
        )
        await session.run(
            """
            CREATE (f:File {
                project_id: $slug,
                path: 'Sources/Wallet.swift',
                body_hash: $body_hash
            })
            """,
            slug="tron-kit",
            body_hash=current_body_hash,
        )

    swift_file.write_text(
        "struct Wallet { let id: Int; let chainId: Int }\n", encoding="utf-8"
    )

    report = await detect_project_stale_files(
        driver,
        project=ProjectInfo(
            slug="tron-kit",
            name="tron-kit",
            tags=[],
            relative_path="TronKit.Swift",
            language_profile="swift_kit",
        ),
        workspace_root=repo_root,
        ignore_globs=[],
    )

    assert report.requires_reingest is True
    assert report.project_reason is None
    assert len(report.stale_files) == 1
    assert report.stale_files[0]["path"] == "Sources/Wallet.swift"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_project_stale_files_treats_null_finished_at_as_stale(
    driver: AsyncDriver,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repos"
    repo_path = repo_root / "TronKit.Swift"
    swift_file = repo_path / "Sources" / "Wallet.swift"
    swift_file.parent.mkdir(parents=True)
    swift_file.write_text("struct Wallet {}\n", encoding="utf-8")

    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $slug,
                p.tags = [],
                p.relative_path = $relative_path,
                p.language_profile = 'swift_kit'
            """,
            slug="tron-kit",
            relative_path="TronKit.Swift",
        )
        await session.run(
            """
            CREATE (r:IngestRun {
                run_id: 'run-null',
                project: $slug,
                extractor_name: 'symbol_index_swift',
                started_at: datetime($started_at),
                finished_at: null
            })
            """,
            slug="tron-kit",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        await session.run(
            """
            CREATE (f:File {
                project_id: $slug,
                path: 'Sources/Wallet.swift',
                body_hash: 'abc'
            })
            """,
            slug="tron-kit",
        )

    report = await detect_project_stale_files(
        driver,
        project=ProjectInfo(
            slug="tron-kit",
            name="tron-kit",
            tags=[],
            relative_path="TronKit.Swift",
            language_profile="swift_kit",
        ),
        workspace_root=repo_root,
        ignore_globs=[],
    )

    assert report.requires_reingest is True
    assert report.project_reason == "ingest_run_unfinished"
    assert len(report.stale_files) == 1
    assert report.stale_files[0]["reason"] == "ingest_run_unfinished"
