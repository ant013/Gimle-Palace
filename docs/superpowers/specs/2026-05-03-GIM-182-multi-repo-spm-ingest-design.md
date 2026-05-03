---
slug: multi-repo-spm-ingest
status: proposed (rev2)
branch: feature/GIM-182-multi-repo-spm-ingest
paperclip_issue: 182
spec_implements_slice: 4 (per docs/roadmap.md §3 CX queue item 3)
authoring_team: Claude (Board+Claude brainstorm); CX implements
predecessor: 278dfcc (docs(roadmap) PR #78 merged into develop tip)
date: 2026-05-03
rev2_changes: |
  - Drop register_parent_mount MCP tool (param-only on register_project); F8 deferred.
  - Rename app project slug to uw-ios-app to avoid collision with bundle slug uw-ios.
  - Async bundle ingest: kickoff returns run_id immediately; new bundle_status(run_id) tool.
  - Pydantic v2 models replace frozen dataclasses (datetime tz validation, JSON serialization).
  - Split failed_slugs into query_failed / ingest_failed / never_ingested.
  - Fix oldest/newest member ingest tracking (was buggy MIN computation).
  - :Bundle.group_id = "bundle/<name>" namespacing per CLAUDE.md pattern.
  - Path traversal hardening: regex on relative_path/parent_mount + path_resolver assertion.
  - sha256sum verification post-rsync.
  - delete_bundle MCP tool for failed-smoke cleanup.
  - register-uw-ios-bundle.sh + uw-ios-bundle-manifest.json as concrete deliverables.
  - Per-module 90% coverage gate on 3 modules (bundle, find_references, runner).
  - Smoke gate: uw-ios-app=ok mandatory + ≥40/41 overall.
  - Phase 1.2 CR invariant-restate codified.
  - Failure-mode taxonomy enumerated.
  - Mention parser, log rotation, mtime-guard, disk budget, UID/permissions hardening.
---

# GIM-182 — Multi-repo SPM ingest (Slice 4) — rev2

## 1. Context

`docs/roadmap.md` §3 lists Slice 4 ("Multi-repo SPM ingest") as the third
launch-critical CX item. After GIM-128 (Swift extractor for `unstoppable-
wallet-ios` itself) and the planned C/C++/Obj-C iOS extractor land, palace-
mcp can index UW-iOS source — but only the app-level repo. UW-iOS imports
~40 first-party Swift Kits maintained by HorizontalSystems; without them
the symbol graph cannot resolve `EvmKit.Address`, `Eip20Kit.Erc20Adapter`,
`MarketKit.Coin`, etc.

Slice 4 ships the multi-repo capability: index UW-iOS plus 40 HS Kits as
a **bundle** (a virtual project that aggregates per-Kit indexes), so a
single `palace.code.find_references(qualified_name="EvmKit.Address",
project="uw-ios")` resolves usages across all 41 repos.

This is the **Phase 1 launch trigger**. After Slice 4 merges, the operator
can run useful queries against the real production UW iOS codebase.

**Authoring split** (per operator decision 2026-05-03 in `docs/roadmap.md`
§3 Phase 1):
- Spec authored by Board + Claude.
- Implementation by CX paperclip team via the standard 7-phase chain.

**Predecessor SHA**: `278dfcc` (`develop` tip, docs(roadmap) PR #78 merge).

**Related artefacts** (must read before implementation):
- `docs/roadmap.md` §3 Phase 1 launch path.
- `docs/research/extractor-library/` — 45-item inventory; this slice
  expands #21 Symbol Index Extractor across multiple repos.
- `docs/superpowers/specs/2026-04-27-101a-extractor-foundation-design.md`
  §4.2 — `:Project` Neo4j entity; this slice adds `:Bundle` parallel.
- ADR §ARCHITECTURE D2 — Hybrid Tantivy + Neo4j; this slice respects
  the boundary.
- ADR §ARCHITECTURE D5 — tier-aware deployment defaults; this slice
  attaches `tier` metadata to `:CONTAINS` edges (consumed by importance
  scoring; reader is part of 101a foundation, not a v1-of-this-slice
  responsibility).
- `project_swift_emitter_strategy_2026-05-01.md` — `palace-swift-scip-emit`
  reused per Kit (the emitter binary already supports per-project
  invocation; no changes required for this slice).
- `feedback_silent_scope_reduction.md` — frozen scope §2 below; CR Phase
  3.1 must verify `git diff --name-only` matches scope.
- `feedback_pe_qa_evidence_fabrication.md` — Phase 4.1 SSH-from-iMac
  evidence mandate.

## 2. v1 Scope (frozen)

### IN

1. **Bundle Neo4j entity** — new `:Bundle` label + `:CONTAINS` edges with
   `tier` and `added_at` properties. `:Bundle.group_id = "bundle/<name>"`
   per CLAUDE.md namespacing convention.
2. **5 new MCP tools**:
   - `palace.memory.register_bundle(name, description) -> Bundle`
   - `palace.memory.add_to_bundle(bundle, project, tier) -> None`
   - `palace.memory.bundle_members(bundle) -> list[ProjectRef]`
   - `palace.memory.bundle_status(bundle_or_run_id) -> BundleStatus`
   - `palace.memory.delete_bundle(name, cascade) -> None`
3. **Extension of existing MCP tools**:
   - `palace.code.find_references(qualified_name, project)` — accepts
     bundle slug; expands to per-member iteration; merges results.
   - `palace.ingest.run_extractor(name, project | bundle)` — accepts
     `bundle=` parameter; **returns immediately with `run_id`**;
     ingest runs as background `asyncio.Task` so other MCP tools are
     not blocked for the duration of a 41-member ingest.
   - `palace.ingest.bundle_status(run_id)` — new sibling tool that polls
     the running task's progress (`{state: "running" | "succeeded" |
     "failed", members_done, members_total, members_ok, members_failed,
     ...}`).
   - `palace.memory.register_project(slug, parent_mount?, relative_path?)` —
     adds optional parent-mount triple. **Backward-compatible**: existing
     `:Project` nodes without `parent_mount` continue to resolve to
     `/repos/<slug>` (legacy behavior preserved by default branch in
     `path_resolver`).
4. **One parent mount line** in `docker-compose.yml` for HS Kits:
   `- /Users/Shared/Ios/HorizontalSystems:/repos-hs:ro`. Non-iMac
   contributors override via `docker-compose.override.yml` per existing
   CLAUDE.md convention.
5. **Manifest-driven operator workflow**:
   - `services/palace-mcp/scripts/uw-ios-bundle-manifest.json` (NEW) —
     authoritative list of 41 members with `slug, relative_path, tier`.
   - `services/palace-mcp/scripts/register-uw-ios-bundle.sh` (NEW) —
     idempotent script that reads manifest, calls `register_project` +
     `register_bundle` + `add_to_bundle` for each member; skip-if-exists.
   - `services/palace-mcp/scripts/regen-uw-ios-scip.sh` (NEW) — operator
     dev-Mac orchestrator: per-Kit emit + sha256sum + rsync to iMac,
     with mtime-guard for unchanged Kits.
6. **Operator runbook** at `docs/runbooks/multi-repo-spm-ingest.md` with
   one-time setup, periodic refresh, troubleshooting, cleanup.
7. **3-Kit fixture** (`uw-ios-mini`, `EvmKit-mini`, `Eip20Kit-mini`)
   under `services/palace-mcp/tests/extractors/fixtures/uw-ios-bundle-mini-project/`.
8. **CI manifest-drift check**: `python services/palace-mcp/scripts/diff-manifest-vs-package-resolved.py`
   compares `uw-ios-bundle-manifest.json` to UW-iOS `Package.resolved`;
   fails on drift (catches new HS Kit added upstream + missing in manifest).

### OUT (deferred follow-ups)

| # | Deferred item | Reactivation trigger |
|---|---|---|
| F1 | ThirdParty bundle "uw-ios-full" (~80 repos) | Operator weekly log review reports zero false-positive alerts in own queries against v1 for ≥ 7 days. |
| F2 | Auto-discovery of new Kits in parent_mount | Operator reports manual `register_project` friction (≥ 2 separate occurrences in operator log). |
| F3 | Skip-cache by `.scip` mtime/HEAD-SHA on **ingest** side | Operator reports re-ingest time > 15 min on full bundle. (Generation-side mtime-guard included in v1 per §7.) |
| F4 | Single-query Tantivy across ingest_runs | Bundle query latency > 5 s (measured on real fixtures, not estimate). |
| F5 | Webhook-driven refresh on git push | After F3 delivers cache mechanism. |
| F6 | Concurrent ingest within bundle (parallel SCIP parsing) | After palace-mcp event loop concurrency model lands. |
| F7 | Tier auto-derivation by parent_mount | After F2 delivers auto-discovery. |
| F8 | First-class `palace.memory.register_parent_mount(name, host_path, container_path)` MCP tool | After ≥ 2 distinct parent mounts (HS + ThirdParty) prove the parameter-passing pattern is too brittle. |
| F9 | `:BundleIngestRun` Neo4j entity for atomic full-ingest tracking | Operator needs a single timestamp for "bundle was successfully fully indexed at T"; v1 derives this client-side. |

### Silent-scope-reduction guard

CR Phase 3.1 must paste:

```bash
git diff --name-only origin/develop...HEAD | sort -u
```

Output must match the file list declared in §4 verbatim. Any out-of-scope
file → REQUEST CHANGES per `feedback_silent_scope_reduction.md`.

## 3. Architecture

### 3.1 Three-layer summary

1. **Storage (Neo4j)**: new `:Bundle` entity with `:CONTAINS` edges. Each
   `:Project` retains its existing per-project ingest_run lineage; bundle
   membership is metadata layered on top. **Bundle and project namespaces
   are disjoint** (per §3.4 invariant): the bundle named `uw-ios` cannot
   share a slug with any `:Project`. The UW-iOS app project is registered
   as `uw-ios-app`; the bundle that aggregates app + 40 Kits is `uw-ios`.
2. **Ingest (Python)**: `run_extractor(bundle=...)` schedules an
   `asyncio.Task` for sequential per-member ingest, returns `run_id`
   immediately so the caller is not blocked. Per-member failure isolation;
   summary tracked in a `BundleIngestState` object queryable via
   `bundle_status(run_id)`. Other MCP tools remain responsive throughout
   the run.
3. **Query (Python + Tantivy)**: `find_references` resolves the slug:
   - if a `:Bundle` exists with this name → bundle path (per-member
     iteration + result merge + freshness/health computation).
   - else if a `:Project` exists → existing single-project path,
     unchanged.
   - else → `ProjectOrBundleNotFoundError`.
   Per-Tantivy-segment query overhead is bounded by the per-project
   segment size (existing 101a budget), times 41 members. Real baseline
   to be measured at Phase 4.1; F4 reactivation trigger compares to that
   measurement, not to the spec estimate.

Boundary (per ADR D2): Tantivy per-project segments are NOT merged into
a single index. The bundle layer is a Python-side iterator that calls
existing single-project Tantivy queries and aggregates. This preserves
the supernode-avoidance property and keeps storage costs proportional
to existing per-project budgets.

### 3.2 Diagram

```
┌──────────────────── dev Mac (Operator) ────────────────────┐
│                                                            │
│  /Users/ant013/Ios/HorizontalSystems/                      │
│     ├── unstoppable-wallet-ios/                            │
│     │     ├── scip/index.scip                              │
│     │     └── scip/index.scip.sha256                       │
│     ├── EvmKit.Swift/                                      │
│     │     ├── scip/index.scip                              │
│     │     └── scip/index.scip.sha256                       │
│     └── ... × 41                                           │
│                                                            │
│  regen-uw-ios-scip.sh:                                     │
│    for kit in <41 Kits from manifest>; do                  │
│      if needs_rebuild $kit; then                           │
│        palace-swift-scip-emit --project $kit --output ...  │
│        sha256sum >$kit/scip/index.scip.sha256              │
│      fi                                                    │
│    done                                                    │
│    rsync --partial --append-verify --checksum              │
│      → iMac:/Users/Shared/Ios/HorizontalSystems/           │
└───────────────────────┬────────────────────────────────────┘
                        │ rsync over SSH (key + ControlMaster)
                        ▼
┌──────────────────── iMac (Production) ─────────────────────┐
│                                                            │
│  /Users/Shared/Ios/HorizontalSystems/                      │
│     └── (41 Kits, source + scip + sha256 sidecar)          │
│                                                            │
│  docker-compose.yml:                                       │
│    palace-mcp:                                             │
│      volumes:                                              │
│        - /Users/Shared/Ios/HorizontalSystems:/repos-hs:ro  │
│                                                            │
│  Inside container:                                         │
│    /repos-hs/EvmKit.Swift/scip/index.scip                  │
│    /repos-hs/Eip20Kit.Swift/scip/index.scip                │
│    ... × 41                                                │
│                                                            │
│  Neo4j:                                                    │
│    (:Bundle {                                              │
│      name: "uw-ios",                                       │
│      group_id: "bundle/uw-ios"                             │
│    })                                                      │
│       -[:CONTAINS {tier: "user", added_at}]                │
│         → (:Project {slug: "uw-ios-app",                   │
│                       group_id: "project/uw-ios-app"})     │
│       -[:CONTAINS {tier: "first-party", added_at}]         │
│         → (:Project {slug: "evm-kit"})                     │
│       ... × 40 edges                                       │
│                                                            │
│  Tantivy: 41 separate index segments (per-project),        │
│           queryable individually; bundle iteration in      │
│           Python at find_references / run_extractor sites. │
└────────────────────────────────────────────────────────────┘
```

### 3.3 Type contracts (Pydantic v2)

palace-mcp uses Pydantic v2 across all MCP tool schemas. Bundle types
follow the same convention: validators on `datetime` enforce tz-aware
UTC, validators on `name`/`slug`/`tier` enforce regex/enum, JSON
serialization is automatic via `model_dump()`.

```python
# src/palace_mcp/memory/models.py — additions
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, field_validator
import re

_BUNDLE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
_PROJECT_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")  # aligned with :Project
_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
_PARENT_MOUNT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,15}$")


class Tier(StrEnum):
    USER = "user"
    FIRST_PARTY = "first-party"
    VENDOR = "vendor"  # reserved for F1 (ThirdParty bundle); not used in v1


class FrozenModel(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}


class Bundle(FrozenModel):
    name: str
    description: str
    group_id: str  # always "bundle/<name>"
    created_at: datetime

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _BUNDLE_NAME_RE.match(v):
            raise ValueError(f"invalid bundle name: {v!r}")
        return v

    @field_validator("created_at")
    @classmethod
    def _check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at must be tz-aware")
        return v.astimezone(timezone.utc)


class ProjectRef(FrozenModel):
    slug: str
    tier: Tier
    added_to_bundle_at: datetime

    @field_validator("added_to_bundle_at")
    @classmethod
    def _check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("added_to_bundle_at must be tz-aware")
        return v.astimezone(timezone.utc)


class BundleStatus(FrozenModel):
    name: str
    members_total: int
    members_fresh_within_7d: int
    members_stale: int
    query_failed_slugs: tuple[str, ...]      # transient query-time failures
    ingest_failed_slugs: tuple[str, ...]     # last_run.status != "success"
    never_ingested_slugs: tuple[str, ...]    # last_run is None
    stale_slugs: tuple[str, ...]
    oldest_member_ingest_at: datetime | None
    newest_member_ingest_at: datetime | None
    as_of: datetime  # snapshot timestamp; caller distinguishes fresh vs cached

    @field_validator("as_of", "oldest_member_ingest_at",
                     "newest_member_ingest_at")
    @classmethod
    def _check_tz_optional(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("datetime must be tz-aware")
        return v.astimezone(timezone.utc)


class IngestRunResult(FrozenModel):
    slug: str
    ok: bool
    run_id: str | None
    error_kind: Literal[
        "file_not_found", "extractor_error", "tantivy_disk_full",
        "neo4j_unavailable", "unknown",
    ] | None
    error: str | None
    duration_ms: int


class BundleIngestState(FrozenModel):
    bundle: str
    run_id: str
    state: Literal["running", "succeeded", "failed"]
    members_total: int
    members_done: int
    members_ok: int
    members_failed: int
    runs: tuple[IngestRunResult, ...]
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
```

### 3.4 Invariants (rev2)

These invariants are spec-mandated and enforced by tests in §8.

1. **Bundle-project namespace disjointness.** `register_bundle(name=X)`
   raises `BundleNameConflictsWithProject` if a `:Project {slug: X}`
   exists. `register_project(slug=X)` raises `ProjectSlugConflictsWithBundle`
   if a `:Bundle {name: X}` exists. UW-iOS app is registered as
   `uw-ios-app`; bundle is `uw-ios`.
2. **Symbol grammar is project-independent.** SCIP symbol grammar
   `scip-swift apple <Module> . <descriptor>` is uniquely identifying
   regardless of which project's ingest_run produced the occurrence.
   Two projects with the same module name (e.g. forks) violate this
   invariant; spec considers fork-name conflicts out-of-scope (rare in
   first-party HS Kits; flagged by adversarial test in §8.20).
3. **Group-id namespacing.** `:Bundle.group_id = "bundle/<name>"`;
   `:Project.group_id = "project/<slug>"`. `:CONTAINS` edges intentionally
   cross group boundaries (bundles are metadata aggregating projects).
   Ingest runs and occurrences for a project remain in `project/<slug>`;
   bundle queries traverse `:CONTAINS` to find member projects.
4. **Backward compatibility for legacy `:Project`.** `:Project` nodes
   created before this slice (without `parent_mount` / `relative_path`)
   resolve to `/repos/<slug>` inside the container. `path_resolver`
   defaults to legacy behavior when both new attributes are absent.
5. **Path resolution is non-escaping.** For any registered project,
   `resolved_container_path` MUST satisfy
   `resolved.startswith(parent_mount_container_path)`. Asserted by
   `path_resolver`; violation raises `PathTraversalDetectedError`.
   Caught at registration time AND at every git-tool / ingest call.

## 4. Component layout

```
services/palace-mcp/src/palace_mcp/
├── memory/
│   ├── models.py                  (EXTEND ~120 LOC: Pydantic v2 Bundle,
│   │                                ProjectRef, BundleStatus,
│   │                                IngestRunResult, BundleIngestState,
│   │                                Tier, validators)
│   ├── bundle.py                  (NEW ~220 LOC: bundle CRUD + freshness)
│   │   ├── register_bundle(name, description) -> Bundle
│   │   ├── add_to_bundle(bundle, project, tier) -> None    # idempotent
│   │   ├── remove_from_bundle(bundle, project) -> None
│   │   ├── bundle_members(bundle) -> tuple[ProjectRef, ...]    # ORDER BY p.slug
│   │   ├── bundle_status(bundle) -> BundleStatus
│   │   ├── delete_bundle(name, cascade) -> None    # cleanup primitive
│   │   ├── compute_bundle_health(members, query_failed) -> BundleStatus
│   │   └── _resolve_slug(slug) -> Literal["bundle"|"project"|"none"]    # 1 Cypher
│   └── register_project.py        (EXTEND ~50 LOC: parent_mount + relative_path
│                                    + namespace conflict guard)
├── code/
│   ├── find_references.py         (EXTEND ~100 LOC: bundle slug detection +
│   │                                per-member merge + bundle_health attach)
│   └── composite/
│       └── (no new file; bundle_health computed inside bundle.py)
├── ingest/
│   ├── runner.py                  (EXTEND ~120 LOC: bundle iteration with
│   │                                async kickoff, BundleIngestState
│   │                                tracking, failure isolation, status
│   │                                polling)
│   ├── bundle_state.py            (NEW ~80 LOC: in-process registry of
│   │                                BundleIngestState by run_id; thread-
│   │                                safe; TTL-bounded for completed runs)
│   └── registry.py                (UNCHANGED)
└── git/
    └── path_resolver.py           (EXTEND ~80 LOC: parent_mount path
                                     resolution, legacy /repos/<slug>
                                     fallback, traversal-prevention assert)

services/palace-mcp/scripts/
├── uw-ios-bundle-manifest.json    (NEW: 41-Kit canonical list)
├── register-uw-ios-bundle.sh      (NEW ~120 LOC: idempotent registration
│                                    via MCP HTTP client; reads manifest;
│                                    pre-flight df check; UID check)
├── regen-uw-ios-scip.sh           (NEW ~140 LOC: dev-Mac orchestrator;
│                                    mtime-guard; sha256sum; --partial
│                                    --append-verify rsync; log rotation)
├── diff-manifest-vs-package-resolved.py  (NEW ~100 LOC: CI drift check)
└── _mcp_client.py                 (NEW ~60 LOC: thin httpx-based MCP
                                     client used by register-uw-ios-
                                     bundle.sh and Phase 4.1 smoke)

docker-compose.yml                 (EXTEND +2 lines: HS parent mount)
.env.example                       (EXTEND +1 line: documentation only;
                                     PALACE_SCIP_INDEX_PATHS now
                                     auto-derived from parent_mount
                                     metadata at startup)
CLAUDE.md                          (EXTEND ~30 lines: §"Currently mounted
                                     projects" → HS row; §"Bundles" new
                                     subsection; reference runbook)

services/palace-mcp/tests/extractors/fixtures/
└── uw-ios-bundle-mini-project/    (NEW)
    ├── REGEN.md                    — operator regen instructions
    ├── manifest.json               — 3-Kit fixture manifest
    ├── uw-ios-mini/                — minimal UW-iOS subset
    │   └── scip/index.scip
    ├── EvmKit-mini/                — minimal EvmKit subset
    │   └── scip/index.scip
    └── Eip20Kit-mini/              — minimal Eip20Kit subset
        └── scip/index.scip

docs/runbooks/
└── multi-repo-spm-ingest.md       (NEW ~250 lines: setup + refresh +
                                     troubleshooting + cleanup +
                                     non-iMac override)

services/palace-mcp/tests/
├── memory/
│   ├── test_bundle.py             (NEW ~360 LOC)
│   ├── test_bundle_security.py    (NEW ~140 LOC: Cypher injection fuzz,
│   │                                path traversal, namespace conflicts)
│   └── test_register_project_parent_mount.py  (NEW ~110 LOC)
├── code/
│   └── test_find_references_bundle.py         (NEW ~280 LOC)
├── ingest/
│   ├── test_bundle_ingest.py                  (NEW ~240 LOC)
│   └── test_bundle_state_polling.py           (NEW ~120 LOC)
└── git/
    └── test_path_resolver_parent_mount.py     (NEW ~100 LOC: legacy
                                                 fallback + traversal
                                                 assert)
```

**Estimated size**: ~870 LOC prod + ~1,250 LOC test + spec + plan +
runbook + manifest.

## 5. Data flow

### 5.1 Async bundle ingest

```
operator on dev Mac:
  $ ./services/palace-mcp/scripts/regen-uw-ios-scip.sh
  → reads manifest.json, builds .scip files via palace-swift-scip-emit
  → mtime-guard skips Kits whose Sources/ are not newer than scip/index.scip
  → sha256sum each .scip → index.scip.sha256
  → rsync --partial --append-verify --checksum to iMac
  → log rotation (10 MB cap × 3 files)
  → exit non-zero on any per-Kit failure (operator inspects log)

operator via MCP client:
  > palace.ingest.run_extractor(name="symbol_index_swift", bundle="uw-ios")
  ← {run_id: "rb-2026-05-03-...", state: "running",
     members_total: 41, started_at: "..."}     # returns IMMEDIATELY

  # other MCP tools continue to work; ingest runs in background.

  > palace.ingest.bundle_status(run_id="rb-2026-05-03-...")
  ← {run_id: ..., state: "running", members_done: 17, members_ok: 17,
     members_failed: 0, ...}                   # poll any time

  > palace.ingest.bundle_status(run_id="rb-2026-05-03-...")
  ← {run_id: ..., state: "succeeded", members_done: 41, members_ok: 41,
     members_failed: 0, completed_at: "...", duration_ms: 412300}
```

Implementation:

```python
# src/palace_mcp/ingest/runner.py — extension
async def run_extractor_bundle(name: str, bundle: str, ctx) -> dict:
    members = await bundle_members(bundle)
    if not members:
        # empty-bundle behavior (per §6.4): ok with summary, no work
        return BundleIngestState(
            bundle=bundle,
            run_id=new_run_id(),
            state="succeeded",
            members_total=0,
            members_done=0,
            members_ok=0,
            members_failed=0,
            runs=(),
            started_at=now_utc(),
            completed_at=now_utc(),
            duration_ms=0,
        ).model_dump()

    state = init_bundle_ingest_state(bundle, members)  # bundle_state.py
    asyncio.create_task(
        _run_bundle_ingest_task(name, bundle, members, state)
    )
    return state.snapshot_for_caller()  # state="running", run_id known


async def _run_bundle_ingest_task(name, bundle, members, state) -> None:
    for member in members:
        run_start = now_utc()
        try:
            run = await run_extractor_single(name=name, project=member.slug)
            update_state(state, IngestRunResult(
                slug=member.slug, ok=True, run_id=run.id,
                error_kind=None, error=None,
                duration_ms=ms_between(run_start, now_utc()),
            ))
        except FileNotFoundError as exc:
            update_state(state, _failure_result(member, exc, "file_not_found"))
        except ExtractorError as exc:
            update_state(state, _failure_result(member, exc, "extractor_error"))
        except Neo4jUnavailable as exc:
            update_state(state, _failure_result(member, exc, "neo4j_unavailable"))
        except TantivyDiskFullError as exc:
            update_state(state, _failure_result(member, exc, "tantivy_disk_full"))
        except Exception as exc:
            update_state(state, _failure_result(member, exc, "unknown"))
    finalize_state(state)  # state="succeeded"|"failed", completed_at, etc.
```

### 5.2 Query flow

```
operator via MCP client:
  > palace.code.find_references(qualified_name="EvmKit.Address",
                                 project="uw-ios")

palace-mcp:
  resolution = await _resolve_slug("uw-ios")    # single Cypher
  if resolution.kind == "bundle":
    members = resolution.members                # already loaded
    occurrences = []
    query_failed = []
    for member in members:
      try:
        occs = await find_in_project(qualified_name, member.slug)
        occurrences.extend(occs)
      except Exception as exc:
        logger.warning("bundle_query_member_failed", extra={
          "bundle": "uw-ios", "slug": member.slug, "error": repr(exc),
        })
        query_failed.append(member.slug)
    health = compute_bundle_health(members, query_failed)
    return {
      "ok": True,
      "occurrences": occurrences,
      "bundle_health": health.model_dump(mode="json"),
    }
  elif resolution.kind == "project":
    # existing single-project path; bundle_health absent
    return await find_in_project(qualified_name, "uw-ios")
  else:
    raise ProjectOrBundleNotFoundError("uw-ios")
```

### 5.3 Bundle health computation (rev2)

```python
def compute_bundle_health(
    members: tuple[ProjectRef, ...],
    query_time_failures: list[str],
) -> BundleStatus:
    now_utc = datetime.now(timezone.utc)
    fresh_window = timedelta(days=7)
    stale_slugs: list[str] = []
    ingest_failed_slugs: list[str] = []
    never_ingested_slugs: list[str] = []
    fresh_count = 0
    oldest: datetime | None = None
    newest: datetime | None = None
    for m in members:
        last_run = get_last_ingest_run(m.slug)
        if last_run is None:
            never_ingested_slugs.append(m.slug)
            continue
        if last_run.status != "success":
            ingest_failed_slugs.append(m.slug)
            continue
        # member ingested successfully; classify freshness
        completed = last_run.completed_at
        if (now_utc - completed) < fresh_window:
            fresh_count += 1
        else:
            stale_slugs.append(m.slug)
        # min/max tracking (rev2 fix — was buggy MIN-only before)
        if oldest is None or completed < oldest:
            oldest = completed
        if newest is None or completed > newest:
            newest = completed
    return BundleStatus(
        name=...,
        members_total=len(members),
        members_fresh_within_7d=fresh_count,
        members_stale=len(stale_slugs),
        query_failed_slugs=tuple(sorted(set(query_time_failures))),
        ingest_failed_slugs=tuple(sorted(set(ingest_failed_slugs))),
        never_ingested_slugs=tuple(sorted(set(never_ingested_slugs))),
        stale_slugs=tuple(sorted(set(stale_slugs))),
        oldest_member_ingest_at=oldest,
        newest_member_ingest_at=newest,
        as_of=now_utc,
    )
```

`fresh_slugs` is intentionally count-only (no list); large bundles with
38/41 fresh members would produce noisy `fresh_slugs` arrays. Caller
computes `fresh = members_total - members_stale - len(query_failed) -
len(ingest_failed) - len(never_ingested)` if needed.

## 6. Error handling

### 6.1 Bundle ingest

- Per-member `try / except` with **enumerated failure-mode taxonomy**
  (per §3.3 `IngestRunResult.error_kind`): `file_not_found`,
  `extractor_error`, `tantivy_disk_full`, `neo4j_unavailable`, `unknown`.
- On per-member exception: log `bundle_ingest_member_failed` with
  `bundle, slug, error_kind, error_repr`, append failure entry to
  `BundleIngestState`. Continue with the next member.
- Outer `try` only wraps the initial `bundle_members` Cypher fetch; if
  that fails, the whole call fails fast (no members to iterate).

### 6.2 Bundle query

- Per-member `try / except`. On exception: log
  `bundle_query_member_failed`, add slug to `query_failed_slugs`,
  continue. Bundle health includes split slugs so the caller distinguishes
  query-time transient from ingest-time persistent failure.

### 6.3 Bundle CRUD invariants

- `register_bundle`:
  - Cannot register the same bundle name twice. Cypher constraint
    `CREATE CONSTRAINT bundle_name IF NOT EXISTS FOR (b:Bundle)
    REQUIRE b.name IS UNIQUE`.
  - Cannot share name with existing `:Project.slug` (raises
    `BundleNameConflictsWithProject`). Implemented by Cypher pre-check.
- `register_project`:
  - Cannot share slug with existing `:Bundle.name` (raises
    `ProjectSlugConflictsWithBundle`).
  - Cannot share slug with another project (existing constraint).
- `add_to_bundle`: Idempotent on duplicate. If `(:Bundle)-[:CONTAINS]→
  (:Project)` already exists, no-op + log `bundle_member_already_present`.
  Returns the existing edge metadata.
- `add_to_bundle`: Single-op per call. No batch API; partial-failure
  semantics are caller's responsibility (`register-uw-ios-bundle.sh`
  retries on transient Neo4j errors via exponential backoff).
- `remove_from_bundle`: No-op + warn log if member not present.
- `delete_bundle(name, cascade)`:
  - `cascade=False`: raise `BundleNonEmpty` if any `:CONTAINS` edges
    exist.
  - `cascade=True`: detach-delete bundle + all `:CONTAINS` edges (does
    NOT delete member projects themselves).
- `bundle_members`: Returns empty tuple if bundle exists but has zero
  members. Raises `BundleNotFoundError` if bundle does not exist.
  Cypher `ORDER BY p.slug ASC` for stable test assertions.
- Bundle name regex: `^[a-z][a-z0-9-]{1,30}$` (aligned with project
  slug regex). Validate before any Cypher; reject otherwise.
- Cypher injection adversarial fuzz test: §8.20.

### 6.4 Empty-bundle behavior

- `find_references(project=<empty-bundle>)` returns
  `{ok: true, occurrences: [], bundle_health: {members_total: 0, ...}}`.
- `run_extractor(bundle=<empty-bundle>)` returns succeeded immediately
  with `members_total: 0, members_ok: 0` (per §5.1 short-circuit).

### 6.5 Path traversal hardening (rev2)

- `relative_path` regex: `^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$`.
  No leading `/`, no `..`, no other path-traversal characters. Validated
  at `register_project` boundary.
- `parent_mount` name regex: `^[a-z][a-z0-9-]{0,15}$`. Validated at
  `register_project` boundary.
- `path_resolver.resolve(slug)` MUST satisfy
  `resolved_path.startswith(parent_mount.container_path)` — assert
  raises `PathTraversalDetectedError` on violation. Tested in §8.21.

### 6.6 Schema migration (backward compatibility)

- Existing `:Project` nodes without `parent_mount` / `relative_path`
  attributes resolve to `/repos/<slug>` inside the container. Default
  branch in `path_resolver`. Tested in `test_path_resolver_legacy_default`.
- Existing single-project queries (`find_references(project="<slug>")`)
  follow the original code path; `bundle_health` is absent. Tested in
  `test_find_references_single_project_unchanged`.
- Existing single-project ingests (`run_extractor(name="...", project="...")`)
  unchanged.

### 6.7 Constraint bootstrap timing

`ensure_custom_schema()` (existing 101a foundation primitive) is
extended at server startup to create the `bundle_name` UNIQUE constraint
idempotently. Race-condition-free via Neo4j's atomic constraint
creation semantics. Verified by `test_ensure_custom_schema_creates_bundle_constraint`.

## 7. Operator workflow

### 7.1 One-time setup on iMac

```bash
# 1. Pre-flight disk budget check.
ssh imac-ssh.ant013.work bash -c '
  free_gb=$(df -g /Users/Shared/Ios | awk "NR==2 {print \$4}")
  if [ "$free_gb" -lt 15 ]; then
    echo "ERROR: need ≥15GB free at /Users/Shared/Ios; have ${free_gb}GB" >&2
    exit 1
  fi
  echo "OK: ${free_gb}GB free"
'

# 2. Clone all 41 repos under HS parent dir.
ssh imac-ssh.ant013.work bash -c '
  mkdir -p /Users/Shared/Ios/HorizontalSystems
  cd /Users/Shared/Ios/HorizontalSystems
  python3 ~/Gimle-Palace/services/palace-mcp/scripts/_clone_kits.py \
    --manifest ~/Gimle-Palace/services/palace-mcp/scripts/uw-ios-bundle-manifest.json \
    --base /Users/Shared/Ios/HorizontalSystems
  # umask discipline for container UID 1000:
  chmod -R go+rX /Users/Shared/Ios/HorizontalSystems
'

# 3. Bring up palace-mcp with HS mount.
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace && docker compose --profile review up -d \
   --force-recreate palace-mcp'   # required after mount addition
```

### 7.2 Initial registration via MCP

`register-uw-ios-bundle.sh` is the single idempotent entry point. It
reads `uw-ios-bundle-manifest.json` and:

1. Calls `register_project(slug, parent_mount="hs", relative_path)`
   for each member (idempotent: skip if `:Project` exists with same slug).
2. Calls `register_bundle(name="uw-ios", description="...")` (idempotent).
3. Calls `add_to_bundle(bundle="uw-ios", project=<slug>, tier=<tier>)`
   for each member (idempotent).

```bash
ssh imac-ssh.ant013.work \
  'bash ~/Gimle-Palace/services/palace-mcp/scripts/register-uw-ios-bundle.sh'
```

Manifest example (`uw-ios-bundle-manifest.json`):

```json
{
  "bundle_name": "uw-ios",
  "bundle_description": "UW iOS app + first-party HorizontalSystems Swift Kits",
  "parent_mount": "hs",
  "members": [
    {"slug": "uw-ios-app", "relative_path": "unstoppable-wallet-ios", "tier": "user"},
    {"slug": "evm-kit", "relative_path": "EvmKit.Swift", "tier": "first-party"},
    {"slug": "eip20-kit", "relative_path": "Eip20Kit.Swift", "tier": "first-party"},
    {"slug": "market-kit", "relative_path": "MarketKit.Swift", "tier": "first-party"},
    {"slug": "hs-toolkit", "relative_path": "HsToolKit.Swift", "tier": "first-party"}
    // ... × 41 entries; canonical list lives ONLY in this file
  ]
}
```

### 7.3 Periodic refresh (after dev Mac Xcode session)

```bash
# On dev Mac:
$ cd ~/Ios/HorizontalSystems
$ bash ~/Android/Gimle-Palace/services/palace-mcp/scripts/regen-uw-ios-scip.sh
```

Script behavior:

1. Reads `uw-ios-bundle-manifest.json`.
2. For each Kit:
   - mtime-guard: if `Sources/**` is not newer than `scip/index.scip`,
     skip rebuild (huge speedup on incremental refresh).
   - Otherwise: run `palace-swift-scip-emit --project <slug> --output ...`.
   - Compute `sha256sum scip/index.scip > scip/index.scip.sha256`.
3. rsync `--partial --append-verify --checksum -e "ssh -o ControlMaster=auto"`
   to iMac. SSH key authentication only (no `sshpass` per
   `reference_imac_ssh_access.md`).
4. Log to `~/Library/Logs/palace-uw-ios-regen.log` with rotation
   (10 MB cap × 3 files via `logrotate`-style in-script rotation).
5. Exit non-zero if any per-Kit step fails; operator inspects log.

```python
# In MCP client:
palace.ingest.run_extractor(name="symbol_index_swift", bundle="uw-ios")
# returns immediately with run_id; ingest runs in background.

palace.ingest.bundle_status(run_id="rb-...")
# poll until state="succeeded" or "failed".
```

### 7.4 Cleanup (failed smoke or migration)

```python
# Delete bundle without deleting member projects:
palace.memory.delete_bundle(name="uw-ios", cascade=True)
```

### 7.5 Daily query usage

```python
palace.code.find_references(
    qualified_name="EvmKit.Address",
    project="uw-ios",
)
# → {ok: true, occurrences: [...], bundle_health: {as_of: ..., ...}}
```

### 7.6 Non-iMac contributors

`docker-compose.override.yml` redirects `/Users/Shared/Ios/HorizontalSystems`
to the contributor's local clone path. Pattern documented in CLAUDE.md.

## 8. Acceptance criteria

1. **`:Bundle` schema** — Cypher constraint on `Bundle.name` uniqueness;
   `:Bundle.group_id = "bundle/<name>"` always set. Verified by
   `test_register_bundle_creates_unique_constrained_node`.
2. **5 new MCP tools registered** — `register_bundle`, `add_to_bundle`,
   `bundle_members`, `bundle_status`, `delete_bundle`. Verified by
   contract tests using real `streamablehttp_client` per GIM-91 wire-
   contract rule.
3. **`palace.code.find_references` bundle expansion** — `project="uw-ios"`
   expands to 41 members; results merged. Verified by
   `test_find_references_bundle_merges_per_member_results`.
4. **`palace.ingest.run_extractor(bundle=)` async kickoff** — returns
   `run_id` within 100 ms even for 41-member bundles; the heavy work
   runs in `asyncio.Task`. Verified by
   `test_bundle_ingest_returns_run_id_immediately` and
   `test_other_mcp_tools_responsive_during_bundle_ingest`.
5. **`palace.ingest.bundle_status(run_id)`** — returns current state and
   per-member progress while task is running; transitions to "succeeded"
   or "failed" on completion. Verified by `test_bundle_status_polling`.
6. **Per-member fail isolation with enumerated taxonomy** — when 1 of 41
   raises `FileNotFoundError`, `ExtractorError`, `Neo4jUnavailable`, or
   `TantivyDiskFullError`, remaining 40 complete and the failed member
   is recorded with the correct `error_kind`. Verified by parametrized
   test across all 4 enumerated kinds + 1 generic.
7. **Bundle health: split failure types** — response contains
   `query_failed_slugs`, `ingest_failed_slugs`, `never_ingested_slugs`
   as separate fields. Verified by
   `test_bundle_health_distinguishes_failure_types`.
8. **Bundle health: oldest/newest tracked correctly** — multiple members
   with different `last_run.completed_at` produce
   `oldest_member_ingest_at = MIN, newest_member_ingest_at = MAX`.
   Verified by `test_bundle_health_min_max_tracking`.
9. **Bundle health: `as_of` set** — every `BundleStatus` response
   includes `as_of` timestamp. Verified by `test_bundle_status_has_as_of`.
10. **`register_project` parent_mount support** — call with
    `parent_mount="hs", relative_path="EvmKit.Swift"` resolves to
    `/repos-hs/EvmKit.Swift` inside the container. Verified by
    `test_register_project_with_parent_mount`.
11. **Backward compatibility for legacy `:Project`** — pre-existing
    project without `parent_mount` resolves to `/repos/<slug>`. Verified
    by `test_path_resolver_legacy_default`.
12. **`palace.git.*` parent_mount path resolution** — `palace.git.log
    project="evm-kit"` reads from `/repos-hs/EvmKit.Swift/.git`. Verified
    by `test_git_log_resolves_through_parent_mount`. Realistic estimate
    60-100 LOC across `path_resolver.py` and per-tool resolution sites.
13. **`palace.git.*` regression for single-project** — `palace.git.log
    project="gimle"` continues to resolve to `/repos/gimle/.git`.
    Verified by `test_git_log_single_project_unchanged`.
14. **Backward compatibility for `find_references` single project** —
    queries follow original code path; `bundle_health` absent. Verified
    by `test_find_references_single_project_unchanged`.
15. **Bundle-project namespace conflict guards** — `register_bundle`
    raises if a `:Project` with same slug exists, and vice versa.
    Verified by `test_namespace_conflict_bidirectional`.
16. **Bundle name regex** — name `^[a-z][a-z0-9-]{1,30}$`; invalid
    names rejected at the Python boundary before Cypher. Verified by
    `test_bundle_name_validation`.
17. **Idempotent `add_to_bundle`** — duplicate add is a no-op. Verified
    by `test_add_to_bundle_idempotent`.
18. **`delete_bundle` semantics** — `cascade=False` raises on non-empty;
    `cascade=True` detaches member edges but does not delete `:Project`
    nodes. Verified by parametrized test.
19. **Empty-bundle behavior** — bundle with 0 members produces
    `find_references` ok with empty results, and `run_extractor` short-
    circuits to succeeded with members_total=0. Verified by 2 tests.
20. **Cypher injection adversarial fuzz** — `register_bundle(name=...)`
    rejects all entries from a 50-string fuzz vector containing Cypher
    syntax. Verified by `test_bundle_name_cypher_injection_fuzz` in
    `test_bundle_security.py`.
21. **Path traversal prevention** — `register_project(relative_path=
    "../../etc")` raises `PathTraversalDetectedError`; same for
    `parent_mount` containing `..`. Verified by 4 parametrized tests.
22. **Group-id namespacing** — `:Bundle.group_id = "bundle/<name>"`,
    `:Project.group_id = "project/<slug>"`; cross-group isolation
    verified by `test_bundle_query_does_not_leak_to_other_groups`.
23. **3-Kit fixture passes E2E test** — fixture under
    `uw-ios-bundle-mini-project/` with three pre-generated `.scip`
    files. Test creates bundle, registers 3 projects, ingests via
    bundle, queries cross-Kit reference, asserts merge results.
    Verified by `test_bundle_ingest_and_query_e2e`.
24. **Pydantic v2 datetime tz validation** — naive datetime in any
    Bundle/ProjectRef/BundleStatus field raises ValidationError.
    Verified by `test_bundle_models_reject_naive_datetime`.
25. **Failure-mode taxonomy on PE-side** — PE tests inject named
    exceptions (`FileNotFoundError`, etc.), not plain `Exception`. CR
    Phase 3.1 verifies test list explicitly.
26. **Ingest tracking in Neo4j is per-project, unchanged** — bundle
    ingest does NOT create new `:IngestRun` shapes; existing per-project
    `:IngestRun` is the source of truth.
27. **Lint / format / type / test gates** — `uv run ruff check`,
    `uv run ruff format --check`, `uv run mypy src/`,
    `uv run pytest --cov=src/palace_mcp --cov-fail-under=85` all green.
28. **Per-module 90% coverage on 3 modules** —
    `pytest --cov=palace_mcp.memory.bundle --cov-fail-under=90`,
    `pytest --cov=palace_mcp.code.find_references --cov-fail-under=90`,
    `pytest --cov=palace_mcp.ingest.runner --cov-fail-under=90`. All
    green. Dotted module paths (not `src/...` filesystem paths).
29. **CI manifest-drift check** — `diff-manifest-vs-package-resolved.py`
    fails CI if `uw-ios-bundle-manifest.json` diverges from UW-iOS
    `Package.resolved`. Verified by adding to `.github/workflows/ci.yml`.
30. **Live smoke on iMac** — operator-driven smoke per §9.4. **Mandatory
    per §9.4.4: `uw-ios-app` slug must be `ok` AND members_ok ≥ 40 of
    41**. SSH-from-iMac evidence captured.
31. **CLAUDE.md updated** — §"Currently mounted projects" reflects HS
    parent mount; new §"Bundles" subsection; §"Extractors" references
    new bundle workflow.
32. **Runbook present** — `docs/runbooks/multi-repo-spm-ingest.md`
    covers one-time setup, periodic refresh, troubleshooting (UID
    permissions, --force-recreate, sha256sum mismatch, smoke cleanup),
    and non-iMac override.

## 9. Verification plan

### 9.1 Pre-implementation (CX CTO Phase 1.1)

1. Confirm branch starts from `278dfcc`.
2. Confirm `palace-swift-scip-emit` from GIM-128 supports per-project
   invocation.
3. Confirm `:Project` Neo4j schema (post-101a foundation) is stable.
4. Confirm Pydantic v2 is in `services/palace-mcp/pyproject.toml`.
5. Confirm `httpx.MockTransport` pattern available for client tests.

### 9.2 Per-task gates

Each implementation task ends with a green test target before the next
task starts. See implementation plan (authored by CX CTO in Phase 1.1).

### 9.3 Post-implementation gates

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest -q
uv run pytest --cov=src/palace_mcp --cov-fail-under=85 -q
uv run pytest --cov=palace_mcp.memory.bundle --cov-fail-under=90 \
  tests/memory/test_bundle.py tests/memory/test_bundle_security.py -q
uv run pytest --cov=palace_mcp.code.find_references --cov-fail-under=90 \
  tests/code/test_find_references_bundle.py -q
uv run pytest --cov=palace_mcp.ingest.runner --cov-fail-under=90 \
  tests/ingest/test_bundle_ingest.py tests/ingest/test_bundle_state_polling.py -q
```

All must exit 0. Output pasted verbatim in CR Phase 3.1 handoff comment.

### 9.4 Live smoke (Phase 4.1, on iMac)

QA performs the procedure on iMac via SSH. Local-Mac evidence not
acceptable per `feedback_pe_qa_evidence_fabrication.md`.

#### 9.4.1 Pre-flight

1. `ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'` —
   capture identity for evidence.
2. Confirm GIM-128 (Swift extractor) live in production palace-mcp.
3. Confirm 41 Kits cloned at
   `/Users/Shared/Ios/HorizontalSystems/<Kit>/`, source + `.scip` +
   `.scip.sha256` present.
4. Confirm container restarted with `--force-recreate` after HS mount
   addition.

#### 9.4.2 Smoke procedure (Python httpx; no `mcp-call`)

```python
# scripts/smoke_uw_ios_bundle.py — bundled in this slice
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from mcp.client.streamable_http import streamablehttp_client

PALACE_MCP_URL = "http://localhost:8080/mcp"

async def call(tool: str, args: dict) -> dict:
    async with streamablehttp_client(PALACE_MCP_URL) as (read, write, _):
        # ... per GIM-91 wire-contract pattern
        result = await invoke(tool, args)
        return result

async def main() -> int:
    # 1. Register bundle.
    await call_script("register-uw-ios-bundle.sh")

    # 2. Verify all 41 .scip files present + sha256 valid (per §6.5).
    verify_sha256_all_kits()

    # 3. Run bundle ingest (async kickoff).
    kickoff = await call(
        "palace.ingest.run_extractor",
        {"name": "symbol_index_swift", "bundle": "uw-ios"},
    )
    run_id = kickoff["run_id"]
    print(f"kickoff: run_id={run_id}, state={kickoff['state']}")

    # 4. Poll status until terminal state.
    while True:
        status = await call("palace.ingest.bundle_status", {"run_id": run_id})
        if status["state"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(15)

    # 5. Run cross-Kit query.
    query = await call(
        "palace.code.find_references",
        {"qualified_name": "EvmKit.Address", "project": "uw-ios"},
    )

    # 6. Capture evidence (printed to stdout for capture in PR body).
    print(json.dumps({
        "ingest_summary": status,
        "query_summary": {
            "occurrences_count": len(query["occurrences"]),
            "bundle_health": query["bundle_health"],
        },
    }, indent=2))

    # 7. Smoke gate (per §9.4.4).
    return assess_smoke_gate(status, query)

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

#### 9.4.3 Run smoke

```bash
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace && uv run python services/palace-mcp/scripts/smoke_uw_ios_bundle.py' \
  | tee /tmp/uw-ios-smoke-$(date +%s).log
```

#### 9.4.4 Smoke gate (mandatory)

Smoke is GREEN iff:

- `ingest_summary.state == "succeeded"` (or `failed` with members_failed
  ≤ 1 and uw-ios-app NOT in failed list)
- `ingest_summary.members_ok >= 40`
- `"uw-ios-app" not in ingest_summary.runs[*].slug WHERE ok=False`
  (the user-tier app project must succeed)
- `query_summary.occurrences_count > 0`
- `query_summary.bundle_health.members_total == 41`
- `"uw-ios-app" not in query_summary.bundle_health.query_failed_slugs +
  ingest_failed_slugs + never_ingested_slugs`

Any failure → smoke RED → REQUEST CHANGES.

#### 9.4.5 Evidence capture (full failure logs, not tail -1)

PR body `## QA Evidence` section MUST include verbatim:

```
$ ssh imac-ssh.ant013.work 'date -u; hostname; uname -a'
<output — hostname matches expected iMac>

$ jq '.ingest_summary' /tmp/uw-ios-smoke-*.log
<full BundleIngestState — all 41 IngestRunResult entries>

$ jq '.query_summary.bundle_health' /tmp/uw-ios-smoke-*.log
<full BundleStatus payload>

$ ssh imac-ssh.ant013.work \
  'cat ~/.paperclip/palace-mcp.log | \
   jq -c "select(.event==\"bundle_ingest_member_failed\")"'
<all per-member failure events with full error_kind + error_repr;
 NOT truncated by tail>
```

#### 9.4.6 Cleanup (smoke succeeded or failed)

If smoke succeeded: bundle persists for production use; no cleanup needed.

If smoke failed and operator wants to retry from scratch:

```python
palace.memory.delete_bundle(name="uw-ios", cascade=True)
# Then re-run register-uw-ios-bundle.sh.
```

## 10. Out of scope (deferred)

See §2 OUT table for reactivation triggers.

## 11. Risks and mitigations

- **41 Kits regen takes too long** — `regen-uw-ios-scip.sh` may run for
  ≥ 30 min on cold builds. Mitigation: source-side mtime-guard slashes
  warm-refresh time; F3 (ingest-side cache) deferred.
- **Tantivy per-run query overhead unknown** — bundle query iterates 41
  segments serially. Real baseline measured at Phase 4.1; F4
  reactivation trigger compares to the measured baseline + 50%, not to
  the spec estimate.
- **Symbol grammar collisions across Kits** — two Kits with same module
  name. Mitigation: HS Kit module names are unique by convention
  (`EvmKit`, `Eip20Kit`); adversarial test §8.20 fuzzes the symbol-
  grammar parser.
- **Bundle membership drift** — operator clones a new Kit on iMac but
  forgets to call `add_to_bundle`. Mitigation: CI manifest-drift check
  (§8.29); F2 (auto-discovery) deferred.
- **`palace.git.*` regression** — parent_mount path resolution change
  may break existing single-project git tools. Mitigation: explicit
  regression test §8.13.
- **Backward compatibility break on legacy `:Project`** — existing
  callers without parent_mount must still work. Mitigation: §8.11
  + path_resolver default branch + Cypher schema migration test.
- **Cypher injection on bundle name** — Mitigation: §6.3 regex + §8.20
  adversarial fuzz.
- **Path traversal on relative_path / parent_mount** — Mitigation:
  §6.5 regex + path_resolver assert + §8.21 tests.
- **Slug-collision: project named same as bundle** — Mitigation: §3.4
  invariant + §8.15 test.
- **Cross-group isolation leak** — Mitigation: §3.4 group_id
  namespacing + §8.22 test.
- **Async bundle ingest leak** — `asyncio.Task` reference loss leaves
  zombie task. Mitigation: `bundle_state.py` registry holds task refs;
  TTL-bounded for completed runs (memory leak prevention).
- **Disk budget exhaustion on iMac** — Mitigation: §7.1 pre-flight
  `df` check; ≥ 15 GB free required.
- **rsync transfer corruption** — Mitigation: sha256sum verification
  per file; `--partial --append-verify --checksum` flags; non-zero
  exit on mismatch.
- **Container UID mismatch on cloned repos** — Mitigation: `chmod -R
  go+rX` step in §7.1; runbook note.
- **Live smoke contamination of production Neo4j** — Mitigation: smoke
  uses production "uw-ios" bundle (intentionally; smoke validates
  production setup); cleanup via `delete_bundle(cascade=True)`
  documented in §7.4.

## 12. Rollout

1. **Phase 1.1 CX CTO Formalize** — verify spec + plan paths, swap any
   placeholders, reassign CX CR.
2. **Phase 1.2 CX CR Plan-first review** — APPROVE comment **MUST**
   include explicit re-statement of these key invariants:
   - Smoke gate requires `uw-ios-app` ok + ≥ 40/41 members ok.
   - `failed_slugs` is split into 3: query / ingest / never_ingested.
   - `register_parent_mount` is NOT a v1 tool (parameter only on
     `register_project`).
   - `:Bundle.group_id = "bundle/<name>"` per CLAUDE.md.
   - Bundle ingest is async (returns run_id immediately).
   This guards against transcription drift between Claude-spec and
   CX-impl.
3. **Phase 2 Implementation** — TDD through plan tasks on
   `feature/GIM-182-multi-repo-spm-ingest`.
4. **Phase 3.1 CX CR Mechanical** — including scope audit, per-module
   coverage gates (3 modules), live-API curl audit (per
   `feedback_pe_qa_evidence_fabrication.md`).
5. **Phase 3.2 CodexArchitectReviewer Adversarial** — required vectors:
   - Cypher injection on bundle name.
   - Path traversal on relative_path / parent_mount.
   - Per-member fail isolation across all 4 enumerated error kinds.
   - Cross-group isolation: bundle in group_id="bundle/foo" doesn't see
     projects in group_id="project/bar" unless explicitly added.
   - Async ingest: zombie task / loop blocking.
   - Slug-collision: bundle-vs-project namespace conflicts.
   - Race: bundle deleted while ingest task is in flight.
6. **Phase 4.1 CX QA Live smoke** on iMac with SSH-from-iMac evidence
   per §9.4.
7. **Phase 4.2 CX CTO Merge**.

## 13. Open questions

- **Exact 41-Kit canonical list** — owned by `uw-ios-bundle-manifest.json`.
  CI manifest-drift check (§8.29) catches drift between manifest and
  UW-iOS `Package.resolved`. If divergence is intentional (Kit added
  for testing only, etc.), operator updates manifest.
- **Async ingest task lifetime** — completed `BundleIngestState` is
  retained in `bundle_state.py` registry with TTL (default 1 h). Long
  enough for operator to poll status post-completion; short enough to
  prevent unbounded memory growth. TTL configurable via env var.
