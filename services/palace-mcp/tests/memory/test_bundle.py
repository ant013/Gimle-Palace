"""Unit tests for palace_mcp.memory.bundle — bundle CRUD and health.

Tests cover:
- Pydantic v2 model validation (Bundle, ProjectRef, BundleStatus, Tier)
- register_bundle: creates node, group_id, namespace conflict
- add_to_bundle: idempotency
- bundle_members: returns sorted list, raises on missing bundle
- bundle_status / compute_bundle_health: failure classification, min/max tracking
- delete_bundle: cascade semantics
- group_id invariant: :Bundle.group_id = "bundle/<name>"
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from palace_mcp.memory.bundle import (
    BundleNameConflictsWithProject,
    BundleNonEmpty,
    BundleNotFoundError,
    add_to_bundle,
    bundle_members,
    bundle_status,
    compute_bundle_health,
    delete_bundle,
    register_bundle,
)
from palace_mcp.memory.models import (
    Bundle,
    BundleStatus,
    IngestRunResult,
    ProjectRef,
    Tier,
)

# ---------------------------------------------------------------------------
# Fake async Neo4j driver / session helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc
_NOW = datetime(2026, 5, 3, 12, 0, 0, tzinfo=_UTC)


class _FakeResult:
    """Minimal async result matching neo4j's AsyncResult protocol."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._i = 0

    def __aiter__(self) -> "_FakeResult":
        self._i = 0
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Single async session serving a queue of results (one per run() call)."""

    def __init__(self, result_queue: list[list[dict[str, Any]]]) -> None:
        self._queue = list(result_queue)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **params: Any) -> _FakeResult:
        self.calls.append((query, params))
        rows = self._queue.pop(0) if self._queue else []
        return _FakeResult(rows)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class _FakeDriver:
    """Fake AsyncDriver that yields sessions from a pre-programmed list."""

    def __init__(self, sessions: list[_FakeSession]) -> None:
        self._sessions = list(sessions)

    def session(self) -> _FakeSession:
        return self._sessions.pop(0) if self._sessions else _FakeSession([])


def _single_session_driver(*result_sets: list[dict[str, Any]]) -> _FakeDriver:
    """Create a driver with ONE session that serves the given result_sets in order."""
    return _FakeDriver([_FakeSession(list(result_sets))])


# ---------------------------------------------------------------------------
# Pydantic v2 model tests
# ---------------------------------------------------------------------------


def test_bundle_model_group_id_format() -> None:
    b = Bundle(
        name="uw-ios",
        description="UW iOS bundle",
        group_id="bundle/uw-ios",
        created_at=_NOW,
    )
    assert b.group_id == "bundle/uw-ios"
    assert b.name == "uw-ios"


def test_bundle_model_rejects_invalid_name() -> None:
    with pytest.raises(ValidationError, match="invalid bundle name"):
        Bundle(
            name="UPPER",
            description="bad",
            group_id="bundle/UPPER",
            created_at=_NOW,
        )


def test_bundle_model_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        Bundle(
            name="uw-ios",
            description="d",
            group_id="bundle/uw-ios",
            created_at=datetime(2026, 5, 3, 12, 0, 0),  # naive — no tzinfo
        )


def test_project_ref_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        ProjectRef(
            slug="evm-kit",
            tier=Tier.FIRST_PARTY,
            added_to_bundle_at=datetime(2026, 5, 3),  # naive
        )


def test_bundle_status_has_three_failure_type_fields() -> None:
    bs = BundleStatus(
        name="uw-ios",
        members_total=3,
        members_fresh_within_7d=1,
        members_stale=1,
        query_failed_slugs=("eip20-kit",),
        ingest_failed_slugs=("market-kit",),
        never_ingested_slugs=("hs-toolkit",),
        stale_slugs=("evm-kit",),
        oldest_member_ingest_at=_NOW - timedelta(days=10),
        newest_member_ingest_at=_NOW,
        as_of=_NOW,
    )
    assert bs.query_failed_slugs == ("eip20-kit",)
    assert bs.ingest_failed_slugs == ("market-kit",)
    assert bs.never_ingested_slugs == ("hs-toolkit",)


def test_tier_enum_values() -> None:
    assert Tier.USER == "user"
    assert Tier.FIRST_PARTY == "first-party"
    assert Tier.VENDOR == "vendor"


# ---------------------------------------------------------------------------
# register_bundle
# ---------------------------------------------------------------------------


async def test_register_bundle_returns_bundle_with_group_id() -> None:
    # Single session: (1) check no project → empty, (2) MERGE Bundle → row
    driver = _single_session_driver(
        [],  # no project with same slug
        [
            {
                "b": {
                    "name": "uw-ios",
                    "description": "UW iOS bundle",
                    "group_id": "bundle/uw-ios",
                    "created_at": _NOW.isoformat(),
                }
            }
        ],
    )

    result = await register_bundle(driver, name="uw-ios", description="UW iOS bundle")

    assert isinstance(result, Bundle)
    assert result.name == "uw-ios"
    assert result.group_id == "bundle/uw-ios"


async def test_register_bundle_raises_on_project_slug_conflict() -> None:
    # check returns a matching project slug → must raise
    driver = _single_session_driver([{"slug": "uw-ios"}])

    with pytest.raises(BundleNameConflictsWithProject, match="uw-ios"):
        await register_bundle(driver, name="uw-ios", description="desc")


async def test_register_bundle_rejects_invalid_name_before_cypher() -> None:
    # driver should NOT be called for invalid names
    driver = _FakeDriver([])  # empty — any call would error
    with pytest.raises(ValueError, match="invalid bundle name"):
        await register_bundle(driver, name="INVALID", description="desc")


# ---------------------------------------------------------------------------
# add_to_bundle
# ---------------------------------------------------------------------------


async def test_add_to_bundle_creates_contains_edge() -> None:
    # Single session: (1) check bundle exists, (2) check project exists, (3) MERGE CONTAINS
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],  # bundle exists
        [{"slug": "evm-kit"}],  # project exists
        [],  # MERGE CONTAINS result unused
    )
    # Should not raise
    await add_to_bundle(
        driver, bundle="uw-ios", project="evm-kit", tier=Tier.FIRST_PARTY
    )


async def test_add_to_bundle_idempotent_on_duplicate() -> None:
    # MERGE semantics make this idempotent — same call twice, same result
    for _ in range(2):
        driver = _single_session_driver(
            [{"b_name": "uw-ios"}],
            [{"slug": "evm-kit"}],
            [],
        )
        await add_to_bundle(
            driver, bundle="uw-ios", project="evm-kit", tier=Tier.FIRST_PARTY
        )


async def test_add_to_bundle_raises_when_bundle_not_found() -> None:
    driver = _single_session_driver([])  # bundle check returns empty

    with pytest.raises(BundleNotFoundError, match="uw-ios"):
        await add_to_bundle(
            driver, bundle="uw-ios", project="evm-kit", tier=Tier.FIRST_PARTY
        )


# ---------------------------------------------------------------------------
# bundle_members
# ---------------------------------------------------------------------------


async def test_bundle_members_returns_sorted_project_refs() -> None:
    # Single session: (1) check bundle exists, (2) get members
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],
        [
            {"slug": "eip20-kit", "tier": "first-party", "added_at": _NOW.isoformat()},
            {"slug": "evm-kit", "tier": "first-party", "added_at": _NOW.isoformat()},
            {"slug": "uw-ios-app", "tier": "user", "added_at": _NOW.isoformat()},
        ],
    )

    refs = await bundle_members(driver, bundle="uw-ios")

    assert len(refs) == 3
    # Cypher ORDER BY p.slug ASC → eip20-kit, evm-kit, uw-ios-app
    assert refs[0].slug == "eip20-kit"
    assert refs[1].slug == "evm-kit"
    assert refs[2].slug == "uw-ios-app"
    assert all(isinstance(r, ProjectRef) for r in refs)


async def test_bundle_members_returns_empty_tuple_for_zero_member_bundle() -> None:
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],
        [],  # no members
    )

    refs = await bundle_members(driver, bundle="uw-ios")
    assert refs == ()


async def test_bundle_members_raises_bundle_not_found() -> None:
    driver = _single_session_driver([])  # bundle does not exist

    with pytest.raises(BundleNotFoundError, match="nonexistent"):
        await bundle_members(driver, bundle="nonexistent")


# ---------------------------------------------------------------------------
# bundle_status
# ---------------------------------------------------------------------------


async def test_bundle_status_has_as_of_timestamp() -> None:
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],
        [
            {
                "slug": "evm-kit",
                "tier": "first-party",
                "added_at": _NOW.isoformat(),
                "last_run_completed_at": (_NOW - timedelta(days=3)).isoformat(),
                "last_run_ok": True,
            }
        ],
    )

    status = await bundle_status(driver, bundle="uw-ios")

    assert status.as_of is not None
    assert status.as_of.tzinfo is not None  # must be tz-aware


async def test_bundle_status_distinguishes_failure_types() -> None:
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],
        [
            {
                "slug": "evm-kit",
                "tier": "first-party",
                "added_at": _NOW.isoformat(),
                "last_run_completed_at": (_NOW - timedelta(days=3)).isoformat(),
                "last_run_ok": True,  # fresh success
            },
            {
                "slug": "eip20-kit",
                "tier": "first-party",
                "added_at": _NOW.isoformat(),
                "last_run_completed_at": (_NOW - timedelta(days=1)).isoformat(),
                "last_run_ok": False,  # ingest failed
            },
            {
                "slug": "market-kit",
                "tier": "first-party",
                "added_at": _NOW.isoformat(),
                "last_run_completed_at": None,  # never ingested
                "last_run_ok": None,
            },
        ],
    )

    status = await bundle_status(driver, bundle="uw-ios")

    assert "eip20-kit" in status.ingest_failed_slugs
    assert "market-kit" in status.never_ingested_slugs
    assert "evm-kit" not in status.ingest_failed_slugs
    assert "evm-kit" not in status.never_ingested_slugs
    assert status.members_total == 3


# ---------------------------------------------------------------------------
# compute_bundle_health — pure function
# ---------------------------------------------------------------------------


def _make_ref(slug: str, tier: Tier = Tier.FIRST_PARTY) -> ProjectRef:
    return ProjectRef(slug=slug, tier=tier, added_to_bundle_at=_NOW)


def _make_run_result(
    slug: str,
    *,
    ok: bool,
    completed_at: datetime | None = None,
    error_kind: str | None = None,
) -> IngestRunResult:
    return IngestRunResult(
        slug=slug,
        ok=ok,
        run_id=None,
        error_kind=error_kind,  # type: ignore[arg-type]
        error=None,
        duration_ms=0,
        completed_at=completed_at,
    )


def test_compute_bundle_health_min_max_tracking() -> None:
    older = _NOW - timedelta(days=5)
    newer = _NOW - timedelta(days=1)
    members = (
        _make_ref("evm-kit"),
        _make_ref("eip20-kit"),
    )
    last_runs = {
        "evm-kit": _make_run_result("evm-kit", ok=True, completed_at=older),
        "eip20-kit": _make_run_result("eip20-kit", ok=True, completed_at=newer),
    }
    status = compute_bundle_health(
        bundle_name="uw-ios",
        members=members,
        last_runs=last_runs,
        query_time_failures=[],
        as_of=_NOW,
    )
    assert status.oldest_member_ingest_at == older
    assert status.newest_member_ingest_at == newer


def test_compute_bundle_health_all_three_failure_buckets() -> None:
    members = (
        _make_ref("evm-kit"),  # success + fresh
        _make_ref("eip20-kit"),  # ingest failed
        _make_ref("market-kit"),  # never ingested
    )
    last_runs = {
        "evm-kit": _make_run_result(
            "evm-kit", ok=True, completed_at=_NOW - timedelta(days=1)
        ),
        "eip20-kit": _make_run_result(
            "eip20-kit", ok=False, error_kind="extractor_error"
        ),
        # market-kit absent → never_ingested
    }
    status = compute_bundle_health(
        bundle_name="uw-ios",
        members=members,
        last_runs=last_runs,
        query_time_failures=["hs-toolkit"],
        as_of=_NOW,
    )
    assert status.members_total == 3
    assert status.members_fresh_within_7d == 1
    assert "eip20-kit" in status.ingest_failed_slugs
    assert "market-kit" in status.never_ingested_slugs
    assert "hs-toolkit" in status.query_failed_slugs


def test_compute_bundle_health_empty_bundle() -> None:
    status = compute_bundle_health(
        bundle_name="uw-ios",
        members=(),
        last_runs={},
        query_time_failures=[],
        as_of=_NOW,
    )
    assert status.members_total == 0
    assert status.members_fresh_within_7d == 0
    assert status.oldest_member_ingest_at is None
    assert status.newest_member_ingest_at is None


def test_compute_bundle_health_stale_member() -> None:
    old = _NOW - timedelta(days=10)
    members = (_make_ref("evm-kit"),)
    last_runs = {
        "evm-kit": _make_run_result("evm-kit", ok=True, completed_at=old),
    }
    status = compute_bundle_health(
        bundle_name="uw-ios",
        members=members,
        last_runs=last_runs,
        query_time_failures=[],
        as_of=_NOW,
    )
    assert status.members_stale == 1
    assert "evm-kit" in status.stale_slugs


# ---------------------------------------------------------------------------
# delete_bundle
# ---------------------------------------------------------------------------


async def test_delete_bundle_cascade_false_raises_on_non_empty() -> None:
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],  # bundle exists
        [{"member_count": 3}],  # has members
    )

    with pytest.raises(BundleNonEmpty, match="uw-ios"):
        await delete_bundle(driver, name="uw-ios", cascade=False)


async def test_delete_bundle_cascade_true_calls_detach_delete() -> None:
    session = _FakeSession(
        [
            [{"b_name": "uw-ios"}],  # bundle exists
            [],  # DELETE / DETACH DELETE
        ]
    )
    driver = _FakeDriver([session])

    await delete_bundle(driver, name="uw-ios", cascade=True)

    # Verify DELETE was called in Cypher (checks the detach semantics)
    assert any("DELETE" in call[0] for call in session.calls)


async def test_delete_bundle_cascade_false_ok_when_empty() -> None:
    driver = _single_session_driver(
        [{"b_name": "uw-ios"}],
        [{"member_count": 0}],  # zero members
        [],  # DELETE bundle node
    )
    # Should not raise
    await delete_bundle(driver, name="uw-ios", cascade=False)


async def test_delete_bundle_raises_not_found() -> None:
    driver = _single_session_driver([])  # bundle not found

    with pytest.raises(BundleNotFoundError, match="nonexistent"):
        await delete_bundle(driver, name="nonexistent", cascade=False)


# ---------------------------------------------------------------------------
# Spec §3.4 invariant 3 — group_id = "bundle/<name>"
# ---------------------------------------------------------------------------


async def test_register_bundle_group_id_is_bundle_slash_name() -> None:
    driver = _single_session_driver(
        [],  # no conflict
        [
            {
                "b": {
                    "name": "evm-kit",
                    "description": "EVM Kit bundle",
                    "group_id": "bundle/evm-kit",
                    "created_at": _NOW.isoformat(),
                }
            }
        ],
    )

    result = await register_bundle(driver, name="evm-kit", description="EVM Kit bundle")
    assert result.group_id == "bundle/evm-kit"
