import pytest

from palace_mcp.extractors.code_ownership.checkpoint import (
    delete_checkpoint,
    has_file_state_baseline,
    load_checkpoint,
    update_checkpoint,
)
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


@pytest.mark.asyncio
async def test_load_checkpoint_returns_none_on_first_run(driver):
    await ensure_ownership_schema(driver)
    cp = await load_checkpoint(driver, project_id="gimle")
    assert cp is None


@pytest.mark.asyncio
async def test_update_then_load_roundtrip(driver):
    await ensure_ownership_schema(driver)
    await update_checkpoint(
        driver,
        project_id="gimle",
        head_sha="abcdef0123456789abcdef0123456789abcdef01",
        run_id="11111111-1111-1111-1111-111111111111",
    )
    cp = await load_checkpoint(driver, project_id="gimle")
    assert cp is not None
    assert cp.last_head_sha == "abcdef0123456789abcdef0123456789abcdef01"
    assert cp.run_id == "11111111-1111-1111-1111-111111111111"
    assert cp.last_completed_at.tzinfo is not None


@pytest.mark.asyncio
async def test_update_overwrites_existing(driver):
    await ensure_ownership_schema(driver)
    await update_checkpoint(
        driver,
        project_id="gimle",
        head_sha="aaaa" * 10,
        run_id="run-1",
    )
    await update_checkpoint(
        driver,
        project_id="gimle",
        head_sha="bbbb" * 10,
        run_id="run-2",
    )
    cp = await load_checkpoint(driver, project_id="gimle")
    assert cp is not None
    assert cp.last_head_sha == "bbbb" * 10
    assert cp.run_id == "run-2"


@pytest.mark.asyncio
async def test_delete_checkpoint_removes_existing(driver):
    await ensure_ownership_schema(driver)
    await update_checkpoint(
        driver,
        project_id="gimle",
        head_sha="aaaa" * 10,
        run_id="run-1",
    )

    await delete_checkpoint(driver, project_id="gimle")

    cp = await load_checkpoint(driver, project_id="gimle")
    assert cp is None


@pytest.mark.asyncio
async def test_has_file_state_baseline_tracks_sidecar_rows(driver):
    await ensure_ownership_schema(driver)

    assert await has_file_state_baseline(driver, project_id="gimle") is False

    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:OwnershipFileState {project_id: 'gimle', path: 'a.py'})
            SET s.status = 'processed',
                s.no_owners_reason = null
            """
        )

    assert await has_file_state_baseline(driver, project_id="gimle") is True
