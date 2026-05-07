"""Unit tests for cross_repo_version_skew neo4j_writer.

Guards against the id/run_id schema mismatch (GIM-218 Phase 4.1 finding):
runner.py creates IngestRun with {id: ...} but writer was matching {run_id: ...}.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.cross_repo_version_skew.models import RunSummary
from palace_mcp.extractors.cross_repo_version_skew.neo4j_writer import (
    _WRITE_EXTRAS_CYPHER,
    _write_run_extras,
)


def test_write_extras_cypher_matches_on_id_not_run_id() -> None:
    """_WRITE_EXTRAS_CYPHER must use {id: $run_id} — the key runner.py creates."""
    assert "IngestRun {id: $run_id}" in _WRITE_EXTRAS_CYPHER
    assert "IngestRun {run_id:" not in _WRITE_EXTRAS_CYPHER


@pytest.mark.asyncio
async def test_write_run_extras_passes_run_id_as_id_key() -> None:
    """_write_run_extras must pass run_id to the {id: ...} MATCH — not {run_id: ...}."""
    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None

    summary = RunSummary(
        mode="project",
        target_slug="gimle",
        member_count=1,
        target_status_indexed_count=1,
        skew_groups_total=0,
        skew_groups_major=0,
        skew_groups_minor=0,
        skew_groups_patch=0,
        skew_groups_unknown=0,
        aligned_groups_total=0,
        warnings_purl_malformed_count=0,
    )
    await _write_run_extras(driver, run_id="test-run-id-123", summary=summary)

    cypher_arg = session.run.await_args.args[0]
    kwargs = session.run.await_args.kwargs
    assert cypher_arg is _WRITE_EXTRAS_CYPHER
    # run_id is passed as the value for $run_id, which maps to Neo4j {id: ...}
    assert kwargs["run_id"] == "test-run-id-123"
    assert kwargs["mode"] == "project"
    assert kwargs["target_slug"] == "gimle"
