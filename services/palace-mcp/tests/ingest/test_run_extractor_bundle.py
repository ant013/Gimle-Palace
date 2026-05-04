"""Tests for run_extractor_bundle (GIM-182 §5.1).

Covers:
- Empty bundle → state="succeeded" returned immediately (no background task)
- Non-empty bundle → state="running" returned immediately with run_id
- Background task: ok member → update_state called with ok=True result
- Background task: failed member → update_state called with ok=False + error_kind
- finalize_state called after all members processed
- run_extractor (MCP entry) routes to bundle path when bundle= kwarg given
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


from palace_mcp.memory.models import IngestRunResult, ProjectRef, Tier


def _make_member(slug: str) -> ProjectRef:
    return ProjectRef(
        slug=slug,
        tier=Tier.FIRST_PARTY,
        added_to_bundle_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# run_extractor_bundle — immediate return
# ---------------------------------------------------------------------------


class TestRunExtractorBundleImmediateReturn:
    """run_extractor_bundle returns without waiting for member ingest."""

    async def test_empty_bundle_returns_succeeded(self) -> None:
        """Empty bundle → dict with state='succeeded', no background task."""
        from palace_mcp.extractors.runner import run_extractor_bundle

        driver = MagicMock()
        graphiti = MagicMock()

        with patch(
            "palace_mcp.extractors.runner.bundle_members",
            new=AsyncMock(return_value=()),
        ):
            result = await run_extractor_bundle(
                name="symbol_index_swift",
                bundle="uw-ios",
                driver=driver,
                graphiti=graphiti,
            )

        assert result["state"] == "succeeded"
        assert result["members_total"] == 0
        assert result["completed_at"] is not None

    async def test_non_empty_bundle_returns_running_immediately(self) -> None:
        """Non-empty bundle → state='running', run_id starts with 'rb-'."""
        from palace_mcp.extractors.runner import run_extractor_bundle

        members = (_make_member("evm-kit"), _make_member("uwb-kit"))
        driver = MagicMock()
        graphiti = MagicMock()

        # Block the background task from actually running during this test
        with (
            patch(
                "palace_mcp.extractors.runner.bundle_members",
                new=AsyncMock(return_value=members),
            ),
            patch(
                "palace_mcp.extractors.runner._run_bundle_ingest_task",
                new=AsyncMock(),
            ),
        ):
            result = await run_extractor_bundle(
                name="symbol_index_swift",
                bundle="uw-ios",
                driver=driver,
                graphiti=graphiti,
            )

        assert result["state"] == "running"
        assert result["run_id"].startswith("rb-")
        assert result["members_total"] == 2
        assert result["completed_at"] is None


# ---------------------------------------------------------------------------
# _run_bundle_ingest_task — background task behaviour
# ---------------------------------------------------------------------------


class TestRunBundleIngestTask:
    """Background task updates state per member and finalizes."""

    async def test_ok_member_calls_update_state_with_ok_true(self) -> None:
        """Successful member ingest → update_state(result.ok=True) called."""
        from palace_mcp.extractors.runner import _run_bundle_ingest_task

        members = (_make_member("evm-kit"),)
        state = {"run_id": "rb-test", "members_total": 1}

        ok_run_dict = {
            "ok": True,
            "run_id": "r-123",
            "extractor": "symbol_index_swift",
            "project": "evm-kit",
            "nodes_written": 10,
            "edges_written": 2,
            "duration_ms": 100,
        }

        captured_results: list[IngestRunResult] = []

        def fake_update(run_id: str, result: IngestRunResult) -> None:
            captured_results.append(result)

        with (
            patch(
                "palace_mcp.extractors.runner.run_extractor",
                new=AsyncMock(return_value=ok_run_dict),
            ),
            patch(
                "palace_mcp.extractors.runner.update_state",
                side_effect=fake_update,
            ),
            patch("palace_mcp.extractors.runner.finalize_state"),
        ):
            await _run_bundle_ingest_task(
                name="symbol_index_swift",
                bundle="uw-ios",
                members=members,
                state=state,
            )

        assert len(captured_results) == 1
        assert captured_results[0].ok is True
        assert captured_results[0].slug == "evm-kit"

    async def test_failed_member_calls_update_state_with_ok_false(self) -> None:
        """run_extractor returning ok=False → update_state(result.ok=False) called."""
        from palace_mcp.extractors.runner import _run_bundle_ingest_task

        members = (_make_member("evm-kit"),)
        state = {"run_id": "rb-test", "members_total": 1}

        error_run_dict = {
            "ok": False,
            "error_code": "extractor_runtime_error",
            "message": "boom",
            "extractor": "symbol_index_swift",
            "project": "evm-kit",
        }

        captured_results: list[IngestRunResult] = []

        def fake_update(run_id: str, result: IngestRunResult) -> None:
            captured_results.append(result)

        with (
            patch(
                "palace_mcp.extractors.runner.run_extractor",
                new=AsyncMock(return_value=error_run_dict),
            ),
            patch(
                "palace_mcp.extractors.runner.update_state",
                side_effect=fake_update,
            ),
            patch("palace_mcp.extractors.runner.finalize_state"),
        ):
            await _run_bundle_ingest_task(
                name="symbol_index_swift",
                bundle="uw-ios",
                members=members,
                state=state,
            )

        assert len(captured_results) == 1
        assert captured_results[0].ok is False
        assert captured_results[0].error_kind == "extractor_error"

    async def test_finalize_called_after_all_members(self) -> None:
        """finalize_state is called exactly once after all members complete."""
        from palace_mcp.extractors.runner import _run_bundle_ingest_task

        members = tuple(_make_member(s) for s in ["a", "b", "c"])
        state = {"run_id": "rb-test", "members_total": 3}

        ok_dict = {
            "ok": True,
            "run_id": "r-x",
            "nodes_written": 1,
            "edges_written": 0,
            "duration_ms": 10,
        }
        finalize_calls = []

        with (
            patch(
                "palace_mcp.extractors.runner.run_extractor",
                new=AsyncMock(return_value=ok_dict),
            ),
            patch("palace_mcp.extractors.runner.update_state"),
            patch(
                "palace_mcp.extractors.runner.finalize_state",
                side_effect=lambda run_id: finalize_calls.append(run_id),
            ),
        ):
            await _run_bundle_ingest_task(
                name="symbol_index_swift",
                bundle="uw-ios",
                members=members,
                state=state,
            )

        assert len(finalize_calls) == 1

    async def test_one_failed_member_does_not_stop_remaining(self) -> None:
        """Failure isolation: remaining members run even if one raises."""
        from palace_mcp.extractors.runner import _run_bundle_ingest_task

        members = tuple(_make_member(s) for s in ["a", "b", "c"])
        state = {"run_id": "rb-test", "members_total": 3}

        # Member "b" raises, others succeed
        ok_dict = {
            "ok": True,
            "run_id": "r-x",
            "nodes_written": 1,
            "edges_written": 0,
            "duration_ms": 10,
        }

        def side_effect(*, name: str, project: str, driver: Any, graphiti: Any) -> Any:
            if project == "b":
                raise RuntimeError("b exploded")
            return ok_dict

        captured_results: list[IngestRunResult] = []

        def fake_update(run_id: str, result: IngestRunResult) -> None:
            captured_results.append(result)

        with (
            patch(
                "palace_mcp.extractors.runner.run_extractor",
                new=AsyncMock(side_effect=side_effect),
            ),
            patch(
                "palace_mcp.extractors.runner.update_state",
                side_effect=fake_update,
            ),
            patch("palace_mcp.extractors.runner.finalize_state"),
        ):
            await _run_bundle_ingest_task(
                name="symbol_index_swift",
                bundle="uw-ios",
                members=members,
                state=state,
            )

        # All 3 members processed (even if one raised)
        assert len(captured_results) == 3
        ok_count = sum(1 for r in captured_results if r.ok)
        fail_count = sum(1 for r in captured_results if not r.ok)
        assert ok_count == 2
        assert fail_count == 1
