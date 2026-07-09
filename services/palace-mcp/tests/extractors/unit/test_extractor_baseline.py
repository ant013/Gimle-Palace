from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.baseline import (
    BASELINE_STATUS_VALID,
    ExtractorBaseline,
    build_valid_extractor_baseline,
    delete_extractor_baseline,
    load_extractor_baseline,
    upsert_extractor_baseline,
)


def _mock_driver(single_value: object) -> MagicMock:
    result = AsyncMock()
    result.single = AsyncMock(return_value=single_value)
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_load_extractor_baseline_maps_neo4j_record() -> None:
    updated_at = datetime.now(tz=timezone.utc).isoformat()
    driver = _mock_driver(
        {
            "project_id": "project/uw-ios-app",
            "project_slug": "uw-ios-app",
            "extractor": "symbol_index_swift",
            "baseline_kind": "swift_symbol_scope",
            "state_version": 1,
            "commit_sha": "abc123",
            "indexed_commit": "abc123",
            "scip_digest": "sha256:scip",
            "scip_path": "scip/index.scip",
            "scip_document_count": 10,
            "scip_occurrence_count": 20,
            "body_hash_manifest_digest": "sha256:manifest",
            "file_count": 3,
            "successful_run_id": "run-1",
            "status": BASELINE_STATUS_VALID,
            "invalid_reason": None,
            "updated_at": updated_at,
        }
    )

    baseline = await load_extractor_baseline(
        driver,
        project_id="project/uw-ios-app",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
    )

    assert baseline is not None
    assert baseline.project_id == "project/uw-ios-app"
    assert baseline.commit_sha == "abc123"
    assert baseline.scip_document_count == 10
    assert baseline.updated_at == datetime.fromisoformat(updated_at)


@pytest.mark.asyncio
async def test_load_extractor_baseline_returns_none_without_record() -> None:
    driver = _mock_driver(None)

    baseline = await load_extractor_baseline(
        driver,
        project_id="project/uw-ios-app",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
    )

    assert baseline is None


@pytest.mark.asyncio
async def test_upsert_extractor_baseline_writes_identity_and_payload() -> None:
    driver = _mock_driver(None)
    baseline = ExtractorBaseline(
        project_id="project/uw-ios-app",
        project_slug="uw-ios-app",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
        state_version=1,
        commit_sha="abc123",
        indexed_commit="abc123",
        scip_digest="sha256:scip",
        scip_path="scip/index.scip",
        scip_document_count=10,
        scip_occurrence_count=20,
        body_hash_manifest_digest="sha256:manifest",
        file_count=3,
        successful_run_id="run-1",
        status=BASELINE_STATUS_VALID,
        invalid_reason=None,
        updated_at=datetime.now(tz=timezone.utc),
    )

    await upsert_extractor_baseline(driver, baseline=baseline)

    session = driver.session.return_value.__aenter__.return_value
    query = session.run.await_args.args[0]
    kwargs = session.run.await_args.kwargs
    assert "MERGE (b:ExtractorBaseline" in query
    assert kwargs["project_id"] == "project/uw-ios-app"
    assert kwargs["extractor"] == "symbol_index_swift"
    assert kwargs["baseline_kind"] == "swift_symbol_scope"
    assert kwargs["successful_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_delete_extractor_baseline_executes_delete_query() -> None:
    driver = _mock_driver(None)

    await delete_extractor_baseline(
        driver,
        project_id="project/uw-ios-app",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
    )

    session = driver.session.return_value.__aenter__.return_value
    query = session.run.await_args.args[0]
    assert "ExtractorBaseline" in query
    assert "DELETE b" in query


def test_build_valid_extractor_baseline_sets_valid_status() -> None:
    baseline = build_valid_extractor_baseline(
        project_id="project/uw-ios-app",
        project_slug="uw-ios-app",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
        state_version=1,
        commit_sha="abc123",
        run_id="run-1",
    )

    assert baseline.status == BASELINE_STATUS_VALID
    assert baseline.invalid_reason is None
