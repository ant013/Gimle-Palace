"""Task 11: Byte-stable back-compat snapshot test.

With project=None, the response must equal the captured N+1b snapshot
(modulo query_ms and warnings). Verifies GIM-53 did not break single-project
callers.

To capture the snapshot:
  NEO4J_PASSWORD=... uv run python -c "
import asyncio, json
from neo4j import AsyncGraphDatabase
from palace_mcp.memory.lookup import perform_lookup
from palace_mcp.memory.schema import LookupRequest

async def main():
    driver = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'PASSWORD'))
    req = LookupRequest(entity_type='Issue', limit=20)
    resp = await perform_lookup(driver, req, 'project/gimle')
    print(json.dumps(resp.model_dump(), indent=2))
    await driver.close()

asyncio.run(main())
" > tests/fixtures/lookup_issue_snapshot_n1b_compat.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

SNAPSHOT_PATH = (
    Path(__file__).parent / "fixtures" / "lookup_issue_snapshot_n1b_compat.json"
)


def _normalize(obj: dict[str, Any]) -> dict[str, Any]:
    """Strip volatile fields before comparison."""
    copy = {k: v for k, v in obj.items() if k not in ("query_ms", "warnings")}
    return copy


@pytest.fixture(scope="module")
def neo4j_password() -> str:
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not pw:
        pytest.skip("NEO4J_PASSWORD not set — skipping integration tests")
    return pw


@pytest_asyncio.fixture(scope="module")
async def live_driver(neo4j_password: str):  # type: ignore[no-untyped-def]
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))
    try:
        await driver.verify_connectivity()
    except Exception:
        await driver.close()
        pytest.skip("Could not connect to Neo4j — skipping integration tests")
    yield driver
    await driver.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lookup_default_project_byte_stable(live_driver: Any) -> None:  # type: ignore[no-untyped-def]
    """With project=None, response must match the captured N+1b snapshot."""
    snap_raw = json.loads(SNAPSHOT_PATH.read_text())
    if snap_raw.get("_placeholder"):
        pytest.skip(
            "Snapshot not yet captured — run capture command in module docstring"
        )

    from palace_mcp.memory.lookup import perform_lookup
    from palace_mcp.memory.schema import LookupRequest

    req = LookupRequest(entity_type="Issue", limit=20)
    resp = await perform_lookup(live_driver, req, "project/gimle")
    out = resp.model_dump()

    assert _normalize(out) == _normalize(snap_raw)
