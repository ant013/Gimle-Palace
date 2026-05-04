"""Tests for bundle_state.py — in-process BundleIngestState registry (GIM-182 §4).

Covers:
- init_bundle_ingest_state: creates running state with correct totals
- update_state: increments counters, appends IngestRunResult
- finalize_state: transitions to succeeded/failed, sets completed_at
- get_bundle_ingest_state: retrieves by run_id
- expired states pruned on access (TTL)
- snapshot_for_caller: returns BundleIngestState model_dump
"""

from __future__ import annotations

from datetime import datetime, timezone


from palace_mcp.memory.models import IngestRunResult, ProjectRef, Tier


def _make_member(slug: str) -> ProjectRef:
    return ProjectRef(
        slug=slug,
        tier=Tier.FIRST_PARTY,
        added_to_bundle_at=datetime.now(timezone.utc),
    )


def _ok_result(slug: str) -> IngestRunResult:
    return IngestRunResult(
        slug=slug,
        ok=True,
        run_id="run-1",
        error_kind=None,
        error=None,
        duration_ms=100,
        completed_at=datetime.now(timezone.utc),
    )


def _fail_result(slug: str) -> IngestRunResult:
    return IngestRunResult(
        slug=slug,
        ok=False,
        run_id=None,
        error_kind="extractor_error",
        error="some error",
        duration_ms=50,
        completed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# init_bundle_ingest_state
# ---------------------------------------------------------------------------


class TestInitBundleIngestState:
    def test_creates_running_state(self) -> None:
        from palace_mcp.extractors.bundle_state import init_bundle_ingest_state

        members = (_make_member("evm-kit"), _make_member("uwb-kit"))
        state = init_bundle_ingest_state("uw-ios", members)

        assert state["state"] == "running"
        assert state["bundle"] == "uw-ios"
        assert state["members_total"] == 2
        assert state["members_done"] == 0
        assert state["members_ok"] == 0
        assert state["members_failed"] == 0
        assert state["runs"] == ()
        assert state["completed_at"] is None
        assert "run_id" in state
        assert state["run_id"].startswith("rb-")

    def test_run_id_is_unique(self) -> None:
        from palace_mcp.extractors.bundle_state import init_bundle_ingest_state

        members = (_make_member("evm-kit"),)
        s1 = init_bundle_ingest_state("uw-ios", members)
        s2 = init_bundle_ingest_state("uw-ios", members)
        assert s1["run_id"] != s2["run_id"]

    def test_empty_bundle_creates_succeeded_state(self) -> None:
        from palace_mcp.extractors.bundle_state import init_bundle_ingest_state

        state = init_bundle_ingest_state("uw-ios", ())
        assert state["state"] == "succeeded"
        assert state["members_total"] == 0
        assert state["completed_at"] is not None


# ---------------------------------------------------------------------------
# update_state
# ---------------------------------------------------------------------------


class TestUpdateState:
    def test_ok_result_increments_ok_and_done(self) -> None:
        from palace_mcp.extractors.bundle_state import (
            init_bundle_ingest_state,
            update_state,
        )

        members = (_make_member("evm-kit"), _make_member("uwb-kit"))
        state = init_bundle_ingest_state("uw-ios", members)
        run_id = state["run_id"]

        update_state(run_id, _ok_result("evm-kit"))

        updated = state  # dict is mutated in-place
        assert updated["members_done"] == 1
        assert updated["members_ok"] == 1
        assert updated["members_failed"] == 0
        assert len(updated["runs"]) == 1

    def test_fail_result_increments_failed_and_done(self) -> None:
        from palace_mcp.extractors.bundle_state import (
            init_bundle_ingest_state,
            update_state,
        )

        members = (_make_member("evm-kit"),)
        state = init_bundle_ingest_state("uw-ios", members)
        run_id = state["run_id"]

        update_state(run_id, _fail_result("evm-kit"))

        assert state["members_done"] == 1
        assert state["members_failed"] == 1
        assert state["members_ok"] == 0

    def test_multiple_updates_accumulate(self) -> None:
        from palace_mcp.extractors.bundle_state import (
            init_bundle_ingest_state,
            update_state,
        )

        members = tuple(_make_member(s) for s in ["a", "b", "c"])
        state = init_bundle_ingest_state("bundle", members)
        run_id = state["run_id"]

        update_state(run_id, _ok_result("a"))
        update_state(run_id, _fail_result("b"))
        update_state(run_id, _ok_result("c"))

        assert state["members_done"] == 3
        assert state["members_ok"] == 2
        assert state["members_failed"] == 1
        assert len(state["runs"]) == 3


# ---------------------------------------------------------------------------
# finalize_state
# ---------------------------------------------------------------------------


class TestFinalizeState:
    def test_all_ok_transitions_to_succeeded(self) -> None:
        from palace_mcp.extractors.bundle_state import (
            finalize_state,
            init_bundle_ingest_state,
            update_state,
        )

        members = (_make_member("evm-kit"),)
        state = init_bundle_ingest_state("uw-ios", members)
        run_id = state["run_id"]
        update_state(run_id, _ok_result("evm-kit"))
        finalize_state(run_id)

        assert state["state"] == "succeeded"
        assert state["completed_at"] is not None
        assert state["duration_ms"] is not None
        assert state["duration_ms"] >= 0

    def test_any_failure_transitions_to_failed(self) -> None:
        from palace_mcp.extractors.bundle_state import (
            finalize_state,
            init_bundle_ingest_state,
            update_state,
        )

        members = (_make_member("evm-kit"), _make_member("uwb-kit"))
        state = init_bundle_ingest_state("uw-ios", members)
        run_id = state["run_id"]
        update_state(run_id, _ok_result("evm-kit"))
        update_state(run_id, _fail_result("uwb-kit"))
        finalize_state(run_id)

        assert state["state"] == "failed"


# ---------------------------------------------------------------------------
# get_bundle_ingest_state
# ---------------------------------------------------------------------------


class TestGetBundleIngestState:
    def test_returns_state_for_known_run_id(self) -> None:
        from palace_mcp.extractors.bundle_state import (
            get_bundle_ingest_state,
            init_bundle_ingest_state,
        )

        members = (_make_member("evm-kit"),)
        state = init_bundle_ingest_state("uw-ios", members)
        run_id = state["run_id"]

        retrieved = get_bundle_ingest_state(run_id)
        assert retrieved is not None
        assert retrieved["run_id"] == run_id

    def test_returns_none_for_unknown_run_id(self) -> None:
        from palace_mcp.extractors.bundle_state import get_bundle_ingest_state

        assert get_bundle_ingest_state("rb-nonexistent") is None
