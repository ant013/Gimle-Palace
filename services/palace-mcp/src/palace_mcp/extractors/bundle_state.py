"""In-process BundleIngestState registry (GIM-182 §4).

Tracks async bundle ingest progress by run_id. States are mutable dicts
rather than frozen models so update_state() can mutate counters without
creating a new object per member.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from palace_mcp.memory.models import IngestRunResult, ProjectRef

_registry: dict[str, dict[str, Any]] = {}


def init_bundle_ingest_state(
    bundle: str,
    members: Iterable[ProjectRef],
) -> dict[str, Any]:
    """Create a running state dict for a bundle ingest and register it.

    Returns the mutable state dict (same object stored in registry).
    If members is empty, transitions immediately to succeeded.
    """
    member_list = tuple(members)
    run_id = f"rb-{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)

    if not member_list:
        state: dict[str, Any] = {
            "run_id": run_id,
            "bundle": bundle,
            "state": "succeeded",
            "members_total": 0,
            "members_done": 0,
            "members_ok": 0,
            "members_failed": 0,
            "runs": (),
            "started_at": now,
            "completed_at": now,
            "duration_ms": 0,
        }
    else:
        state = {
            "run_id": run_id,
            "bundle": bundle,
            "state": "running",
            "members_total": len(member_list),
            "members_done": 0,
            "members_ok": 0,
            "members_failed": 0,
            "runs": (),
            "started_at": now,
            "completed_at": None,
            "duration_ms": None,
            "_started_ts": time.monotonic(),
        }

    _registry[run_id] = state
    return state


def update_state(run_id: str, result: IngestRunResult) -> None:
    """Append a member result and update counters in-place."""
    state = _registry[run_id]
    state["members_done"] += 1
    if result.ok:
        state["members_ok"] += 1
    else:
        state["members_failed"] += 1
    state["runs"] = state["runs"] + (result,)


def finalize_state(run_id: str) -> None:
    """Transition state to succeeded or failed and set completed_at."""
    state = _registry[run_id]
    now = datetime.now(timezone.utc)
    started_ts = state.pop("_started_ts", None)
    state["completed_at"] = now
    state["duration_ms"] = (
        int((time.monotonic() - started_ts) * 1000)
        if started_ts is not None
        else 0
    )
    state["state"] = "succeeded" if state["members_failed"] == 0 else "failed"


def get_bundle_ingest_state(run_id: str) -> dict[str, Any] | None:
    """Return the state dict for run_id, or None if not found."""
    return _registry.get(run_id)
