import pytest

from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


@pytest.mark.asyncio
async def test_ensure_ownership_schema_idempotent(driver):
    """Schema bootstrap is idempotent — second call must not raise."""
    await ensure_ownership_schema(driver)
    await ensure_ownership_schema(driver)


@pytest.mark.asyncio
async def test_ownership_schema_constraints_created(driver):
    """After ensure, expected constraints exist."""
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name")
        names = {record["name"] for record in await result.data()}
    assert "ownership_checkpoint_unique" in names
    assert "ownership_file_state_unique" in names


@pytest.mark.asyncio
async def test_ownership_schema_no_relationship_index(driver):
    """rev2 dropped file_owned_by_weight (dead index for traversal queries)."""
    await ensure_ownership_schema(driver)
    async with driver.session() as session:
        result = await session.run("SHOW INDEXES YIELD name")
        names = {record["name"] for record in await result.data()}
    assert "file_owned_by_weight" not in names
