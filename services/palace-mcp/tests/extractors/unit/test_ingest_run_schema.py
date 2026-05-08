"""Unit tests for IngestRun schema unification (GIM-228, S0.1).

Tests confirm both Path A (runner.py/cypher.py) and Path B
(foundation/checkpoint.py) write the canonical fields
`extractor_name` and `project` on every :IngestRun node.

Tests in TestPathACanonicalFields are RED until S0.1 implementation.
Tests in TestPathBUnchanged document the already-correct Path B state.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.cypher import CREATE_INGEST_RUN


def _mock_driver() -> MagicMock:
    result = AsyncMock()
    result.single = AsyncMock(return_value=None)
    result.data = AsyncMock(return_value=[])
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


class TestPathACanonicalFields:
    """CREATE_INGEST_RUN (Path A, runner.py) must include canonical fields."""

    def test_cypher_declares_extractor_name(self) -> None:
        """CREATE_INGEST_RUN Cypher must declare extractor_name property."""
        assert "extractor_name" in CREATE_INGEST_RUN, (
            "Path A CREATE_INGEST_RUN is missing the extractor_name field. "
            "Add `extractor_name: $extractor_name` to cypher.py."
        )

    def test_cypher_declares_project(self) -> None:
        """CREATE_INGEST_RUN Cypher must declare project property."""
        assert "project" in CREATE_INGEST_RUN, (
            "Path A CREATE_INGEST_RUN is missing the project field. "
            "Add `project: $project` to cypher.py."
        )

    def test_cypher_extractor_name_as_parameter(self) -> None:
        """extractor_name must be a Cypher parameter ($extractor_name), not hardcoded."""
        assert "$extractor_name" in CREATE_INGEST_RUN

    def test_cypher_project_as_parameter(self) -> None:
        """project must be a Cypher parameter ($project), not hardcoded."""
        # Accept $project appearing as $project (not just inside $project_id etc.)
        matches = re.findall(r"\$project\b", CREATE_INGEST_RUN)
        assert len(matches) >= 1, "CREATE_INGEST_RUN must use $project parameter"

    @pytest.mark.asyncio
    async def test_runner_passes_extractor_name_and_project(self) -> None:
        """run_extractor must pass extractor_name and project to CREATE_INGEST_RUN."""
        from unittest.mock import patch, MagicMock as MM
        from pathlib import Path

        driver = _mock_driver()
        graphiti = MM()

        from palace_mcp.extractors import runner
        from palace_mcp.extractors.runner import _PrecheckOk

        ok = _PrecheckOk(
            extractor=MM(),
            repo_path=Path("/tmp/fake"),
            group_id="project/gimle",
        )

        with (
            patch.object(runner, "_precheck", return_value=ok),
            patch.object(
                runner,
                "_execute",
                return_value=MM(stats=MM(nodes_written=0, edges_written=0)),
            ),
            patch.object(runner, "_finalize", return_value=(0, 0, [], True)),
        ):
            await runner.run_extractor(
                "hotspot", "gimle", driver=driver, graphiti=graphiti
            )

        # Inspect all session.run calls for the CREATE_INGEST_RUN kwargs
        session = driver.session.return_value
        all_calls = session.run.call_args_list
        # The CREATE call is the first one; find it by checking kwargs
        found = False
        for call in all_calls:
            kwargs = call.kwargs if hasattr(call, "kwargs") else {}
            if "extractor_name" in kwargs and "project" in kwargs:
                assert kwargs["extractor_name"] == "hotspot"
                assert kwargs["project"] == "gimle"
                found = True
                break
        assert found, (
            "runner.py did not pass extractor_name + project kwargs to session.run. "
            f"Calls: {all_calls}"
        )


class TestPathBUnchanged:
    """foundation/checkpoint.py already writes canonical fields — lock it in."""

    def test_path_b_cypher_has_extractor_name(self) -> None:
        from palace_mcp.extractors.foundation import checkpoint as cp

        assert "extractor_name" in cp._WRITE_INGEST_RUN_CYPHER

    def test_path_b_cypher_has_project(self) -> None:
        from palace_mcp.extractors.foundation import checkpoint as cp

        assert "project" in cp._WRITE_INGEST_RUN_CYPHER

    @pytest.mark.asyncio
    async def test_path_b_create_ingest_run_passes_fields(self) -> None:
        from palace_mcp.extractors.foundation.checkpoint import create_ingest_run

        driver = _mock_driver()
        await create_ingest_run(
            driver, run_id="r1", project="gimle", extractor_name="heartbeat"
        )
        session = driver.session.return_value
        call_str = str(session.run.call_args_list)
        assert "gimle" in call_str
        assert "heartbeat" in call_str
