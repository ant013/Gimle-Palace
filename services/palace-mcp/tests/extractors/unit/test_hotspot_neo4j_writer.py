from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction
from palace_mcp.extractors.hotspot.neo4j_writer import (
    PHASE_1_CYPHER,
    PHASE_3_CYPHER,
    PHASE_4_EVICT_CYPHER,
    PHASE_5_DEAD_CYPHER,
    write_file_and_functions,
)


@pytest.mark.asyncio
async def test_phase1_passes_correct_params():
    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None

    pf = ParsedFile(
        path="src/foo.py",
        language="python",
        functions=(
            ParsedFunction(
                name="bar",
                start_line=10,
                end_line=20,
                ccn=4,
                parameter_count=2,
                nloc=10,
            ),
        ),
    )
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    await write_file_and_functions(
        driver,
        project_id="gimle",
        parsed_file=pf,
        run_started_at=run_at,
    )
    cypher_arg, params = session.run.await_args.args[0], session.run.await_args.args[1]
    assert cypher_arg is PHASE_1_CYPHER
    assert params["project_id"] == "gimle"
    assert params["path"] == "src/foo.py"
    assert params["ccn_total"] == 4
    assert params["run_started_at"] == run_at.isoformat()
    assert params["functions"] == [
        {
            "name": "bar",
            "start_line": 10,
            "end_line": 20,
            "ccn": 4,
            "parameter_count": 2,
            "nloc": 10,
            "language": "python",
        }
    ]


def test_phase1_cypher_sets_complexity_status_fresh():
    assert "complexity_status = 'fresh'" in PHASE_1_CYPHER


def test_phase3_cypher_sets_complexity_status_fresh():
    assert "complexity_status = 'fresh'" in PHASE_3_CYPHER


def test_phase5_cypher_sets_complexity_status_stale():
    assert "complexity_status = 'stale'" in PHASE_5_DEAD_CYPHER


def test_phase4_cypher_uses_last_run_at_cutoff():
    assert "fn.last_run_at < datetime($run_started_at)" in PHASE_4_EVICT_CYPHER
    assert "DETACH DELETE fn" in PHASE_4_EVICT_CYPHER


def test_no_writer_set_on_file_project_id_or_path():
    forbidden = ("SET f.project_id", "SET f.path")
    for cypher in (PHASE_1_CYPHER, PHASE_3_CYPHER, PHASE_5_DEAD_CYPHER):
        for f in forbidden:
            assert f not in cypher


@pytest.mark.asyncio
async def test_fetch_churn_builds_correct_cypher_and_cutoff():
    from palace_mcp.extractors.hotspot.churn_query import CHURN_CYPHER, fetch_churn

    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    fake_records = [{"path": "src/a.py", "churn": 12}]

    class FakeResult:
        def __aiter__(self):
            self._idx = 0
            return self

        async def __anext__(self):
            if self._idx >= len(fake_records):
                raise StopAsyncIteration
            v = fake_records[self._idx]
            self._idx += 1
            return v

    session.run.return_value = FakeResult()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None

    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    paths = ["src/a.py", "src/b.py"]
    out = await fetch_churn(
        driver,
        project_id="gimle",
        paths=paths,
        window_days=90,
        run_started_at=run_at,
    )
    cypher_arg, params = session.run.await_args.args[0], session.run.await_args.args[1]
    assert cypher_arg is CHURN_CYPHER
    assert params["project_id"] == "gimle"
    assert params["paths"] == paths
    assert params["cutoff"] == "2026-02-03T12:00:00+00:00"
    assert out["src/a.py"] == 12
    assert out["src/b.py"] == 0


@pytest.mark.asyncio
async def test_write_hotspot_score_passes_correct_params():
    from palace_mcp.extractors.hotspot.neo4j_writer import write_hotspot_score

    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    await write_hotspot_score(
        driver,
        project_id="gimle",
        path="src/foo.py",
        churn=12,
        score=2.45,
        window_days=90,
        run_started_at=run_at,
    )
    params = session.run.await_args.args[1]
    assert params == {
        "project_id": "gimle",
        "path": "src/foo.py",
        "churn": 12,
        "score": 2.45,
        "window_days": 90,
        "run_started_at": run_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_evict_stale_functions_passes_run_started_at():
    from palace_mcp.extractors.hotspot.neo4j_writer import evict_stale_functions

    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    await evict_stale_functions(driver, project_id="gimle", run_started_at=run_at)
    assert session.run.await_args.args[1] == {
        "project_id": "gimle",
        "run_started_at": run_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_mark_dead_files_zero_passes_alive_paths():
    from palace_mcp.extractors.hotspot.neo4j_writer import mark_dead_files_zero

    driver = MagicMock()
    session = MagicMock()
    session.run = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    driver.session.return_value.__aexit__.return_value = None
    run_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    alive = ["src/a.py", "src/b.py"]
    await mark_dead_files_zero(
        driver,
        project_id="gimle",
        alive_paths=alive,
        run_started_at=run_at,
    )
    assert session.run.await_args.args[1] == {
        "project_id": "gimle",
        "alive_paths": alive,
        "run_started_at": run_at.isoformat(),
    }
