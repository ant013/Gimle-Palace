---
slug: multi-repo-spm-ingest
status: proposed
branch: feature/GIM-182-multi-repo-spm-ingest
paperclip_issue: 182
spec_implements_slice: 4 (per docs/roadmap.md §3 CX queue item 3)
authoring_team: Claude (Board+Claude brainstorm); CX implements
predecessor: 278dfcc (docs(roadmap) PR #78 merged into develop tip)
date: 2026-05-03
---

# GIM-182 — Multi-repo SPM ingest (Slice 4)

## 1. Context

`docs/roadmap.md` §3 lists Slice 4 ("Multi-repo SPM ingest") as the third
launch-critical CX item. After GIM-128 (Swift extractor for `unstoppable-
wallet-ios` itself) and the planned C/C++/Obj-C iOS extractor land, palace-
mcp can index UW-iOS source — but only the app-level repo. UW-iOS imports
~40 first-party Swift Kits maintained by HorizontalSystems; without them
the symbol graph cannot resolve `EvmKit.Address`, `Eip20Kit.Erc20Adapter`,
`MarketKit.Coin`, etc.

Slice 4 ships the multi-repo capability: index UW-iOS plus 40 HS Kits as
a single virtual project ("bundle"), so a single
`palace.code.find_references(qualified_name="EvmKit.Address",
project="uw-ios")` resolves usages across all 41 repos.

This is the **Phase 1 launch trigger**. After Slice 4 merges, the operator
can run useful queries against the real production UW iOS codebase.

**Authoring split** (per operator decision 2026-05-03 in `docs/roadmap.md`
§3 Phase 1):
- Spec authored by Board + Claude (this document).
- Implementation by CX paperclip team via the standard 7-phase chain.

**Predecessor SHA**: `278dfcc` (`develop` tip, docs(roadmap) PR #78 merge).

**Related artefacts** (must read before implementation):
- `docs/roadmap.md` §3 Phase 1 launch path.
- `docs/research/extractor-library/` — 45-item inventory; this slice
  expands #21 Symbol Index Extractor across multiple repos.
- `docs/superpowers/specs/2026-04-27-101a-extractor-foundation-design.md`
  §4.2 — `:Project` Neo4j entity; this slice adds `:Bundle` parallel.
- ADR §ARCHITECTURE D2 — Hybrid Tantivy + Neo4j; this slice respects
  the boundary (Tantivy stays per-project; bundle iteration in Python).
- ADR §ARCHITECTURE D5 — tier-aware deployment defaults; this slice
  attaches `tier` metadata to `:CONTAINS` edges.
- `project_swift_emitter_strategy_2026-05-01.md` — `palace-swift-scip-emit`
  reused per Kit (the emitter binary already supports per-project
  invocation; no changes required for this slice).
- `feedback_silent_scope_reduction.md` — frozen scope §2 below; CR Phase
  3.1 must verify `git diff --name-only` matches scope.

## 2. v1 Scope (frozen)

### IN

1. **Bundle Neo4j entity** — new `:Bundle` label + `:CONTAINS` edges with
   `tier` and `added_at` properties.
2. **4 new MCP tools**:
   - `palace.memory.register_bundle(name, description) -> Bundle`
   - `palace.memory.add_to_bundle(bundle, project, tier) -> None`
   - `palace.memory.bundle_members(bundle) -> list[ProjectRef]`
   - `palace.memory.bundle_status(bundle) -> BundleStatus`
3. **Extension of existing MCP tools**:
   - `palace.code.find_references(qualified_name, project)` — accepts
     bundle slug; expands to per-member iteration; merges results.
   - `palace.ingest.run_extractor(name, project | bundle)` — accepts
     `bundle=` parameter for batch ingest.
   - `palace.memory.register_project(slug, parent_mount?, relative_path?)` —
     adds optional parent-mount triple for the parent-mount mount strategy.
4. **One parent mount line** in `docker-compose.yml` for HS Kits:
   `- /Users/Shared/Ios/HorizontalSystems:/repos-hs:ro`.
5. **Operator workflow** documented in
   `docs/runbooks/multi-repo-spm-ingest.md` covering one-time setup and
   periodic refresh.
6. **3-Kit fixture** for tests (UW-iOS-mini + EvmKit-mini + Eip20Kit-mini)
   under `services/palace-mcp/tests/extractors/fixtures/uw-ios-bundle-mini-project/`.

### OUT (deferred follow-ups)

| # | Deferred item | Reactivation trigger |
|---|---|---|
| F1 | ThirdParty bundle "uw-ios-full" (~80 repos) | After v1 stable for ≥ 7 days |
| F2 | Auto-discovery of new Kits in parent_mount | Operator reports manual `register_project` friction |
| F3 | Skip-cache by `.scip` mtime/HEAD-SHA in bundle ingest | Operator reports re-ingest time > 15 min on full bundle |
| F4 | Single-query Tantivy across ingest_runs | Bundle query latency > 5 s on 41 members |
| F5 | Webhook-driven refresh on git push | After F3 delivers cache mechanism |
| F6 | Concurrent ingest within bundle | After palace-mcp event loop concurrency model lands |
| F7 | Tier auto-derivation by parent_mount | After F2 delivers auto-discovery |

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
   membership is metadata layered on top. No changes to existing project
   schema.
2. **Ingest (Python)**: `run_extractor` iterates bundle members
   sequentially, isolating per-member failures, returning a summary
   report.
3. **Query (Python + Tantivy)**: `find_references` detects bundle slug,
   expands to member list, queries each member's Tantivy segment in
   sequence, merges results, attaches a `bundle_health` payload computed
   from per-member ingest_run staleness.

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
│     ├── unstoppable-wallet-ios/scip/index.scip             │
│     ├── EvmKit.Swift/scip/index.scip                       │
│     ├── Eip20Kit.Swift/scip/index.scip                     │
│     └── ... × 40                                           │
│                                                            │
│  regen-uw-ios-scip.sh:                                     │
│    for kit in <41 Kits>; do                                │
│      palace-swift-scip-emit --project $kit --output ...    │
│    done                                                    │
│    rsync .scip files → iMac                                │
└───────────────────────┬────────────────────────────────────┘
                        │ rsync over SSH
                        ▼
┌──────────────────── iMac (Production) ─────────────────────┐
│                                                            │
│  /Users/Shared/Ios/HorizontalSystems/                      │
│     └── (41 Kits, source + scip files)                     │
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
│    (:Bundle {name: "uw-ios"})                              │
│       -[:CONTAINS {tier: "user"}]→ (:Project {slug: "uw-ios"})         │
│       -[:CONTAINS {tier: "first-party"}]→ (:Project {slug: "evm-kit"}) │
│       ... × 40 edges                                       │
│                                                            │
│  Tantivy: 41 separate index segments (per-project),        │
│           queryable individually; bundle iteration in      │
│           Python at find_references / run_extractor sites. │
└────────────────────────────────────────────────────────────┘
```

### 3.3 Type contracts

```python
# src/palace_mcp/memory/models.py — NEW additions
from datetime import datetime
from dataclasses import dataclass
from enum import StrEnum


class Tier(StrEnum):
    USER = "user"
    FIRST_PARTY = "first-party"
    VENDOR = "vendor"


@dataclass(frozen=True, slots=True)
class Bundle:
    name: str               # ^[a-z][a-z0-9-]{1,30}$
    description: str
    created_at: datetime    # tz-aware UTC


@dataclass(frozen=True, slots=True)
class ProjectRef:
    slug: str
    tier: Tier
    added_to_bundle_at: datetime  # tz-aware UTC


@dataclass(frozen=True, slots=True)
class BundleStatus:
    name: str
    members_total: int
    members_fresh_within_7d: int
    members_stale: int
    members_failed_last_ingest: int
    stale_slugs: list[str]
    failed_slugs: list[str]
    last_full_ingest_at: datetime | None


@dataclass(frozen=True, slots=True)
class IngestRunResult:
    slug: str
    ok: bool
    run_id: str | None
    error: str | None
    duration_ms: int


@dataclass(frozen=True, slots=True)
class BundleIngestSummary:
    bundle: str
    members_total: int
    members_ok: int
    members_failed: int
    runs: list[IngestRunResult]
    duration_ms: int
```

All `datetime` values are tz-aware UTC. Validation enforces this at the
constructor / Cypher boundary.

## 4. Component layout

```
services/palace-mcp/src/palace_mcp/
├── memory/
│   ├── models.py                  (EXTEND ~80 LOC: Tier, Bundle, ProjectRef, BundleStatus dataclasses)
│   ├── bundle.py                  (NEW ~180 LOC: bundle CRUD + freshness)
│   │   ├── register_bundle(name, description) -> Bundle
│   │   ├── add_to_bundle(bundle, project, tier) -> None
│   │   ├── remove_from_bundle(bundle, project) -> None
│   │   ├── bundle_members(bundle) -> list[ProjectRef]
│   │   └── bundle_status(bundle) -> BundleStatus
│   └── register_project.py        (EXTEND ~30 LOC: parent_mount + relative_path)
├── code/
│   ├── find_references.py         (EXTEND ~80 LOC: bundle slug detection + per-member merge)
│   └── composite/
│       └── bundle_health.py       (NEW ~50 LOC: ingest_run staleness check helper)
├── ingest/
│   ├── runner.py                  (EXTEND ~50 LOC: bundle iteration with failure isolation)
│   └── registry.py                (UNCHANGED)
└── git/
    └── path_resolver.py           (EXTEND ~20 LOC: parent_mount path resolution for palace.git.*)

docker-compose.yml                 (EXTEND +2 lines: HS parent mount)
.env.example                       (EXTEND +1 line: HS_PARENT_MOUNT path placeholder)
CLAUDE.md                          (EXTEND ~25 lines: §"Currently mounted projects" → add HS row + bundle workflow link)

services/palace-mcp/scripts/
└── regen-uw-ios-scip.sh           (NEW ~80 LOC: dev-Mac orchestrator + rsync to iMac)

services/palace-mcp/tests/extractors/fixtures/
└── uw-ios-bundle-mini-project/    (NEW)
    ├── REGEN.md                    — operator regen instructions
    ├── uw-ios-mini/                — minimal UW-iOS subset
    ├── EvmKit-mini/                — minimal EvmKit subset
    └── Eip20Kit-mini/              — minimal Eip20Kit subset

docs/runbooks/
└── multi-repo-spm-ingest.md       (NEW: operator workflow + troubleshooting)

services/palace-mcp/tests/
├── memory/
│   ├── test_bundle.py             (NEW ~280 LOC)
│   └── test_register_project_parent_mount.py  (NEW ~80 LOC)
├── code/
│   └── test_find_references_bundle.py         (NEW ~220 LOC)
└── ingest/
    └── test_bundle_ingest.py                  (NEW ~180 LOC)
```

**Estimated size**: ~580 LOC prod + ~760 LOC test + spec + plan + runbook.

## 5. Data flow

### 5.1 Ingest flow

```
operator on dev Mac:
  $ ./services/palace-mcp/scripts/regen-uw-ios-scip.sh
  → builds 41 .scip files via palace-swift-scip-emit per-project
  → rsync to iMac /Users/Shared/Ios/HorizontalSystems/<Kit>/scip/

operator via MCP client:
  > palace.ingest.run_extractor(name="symbol_index_swift", bundle="uw-ios")

palace-mcp (sequential, fail-isolated):
  members = bundle_members("uw-ios")            # 41 entries from Neo4j
  results = []
  start_ts = now()
  for member in members:
    try:
      run = await run_extractor_single(
        name="symbol_index_swift",
        project=member.slug,
      )
      results.append(IngestRunResult(slug=..., ok=True, run_id=run.id, ...))
    except Exception as exc:
      logger.warning("bundle_ingest_member_failed", extra={
        "bundle": "uw-ios", "slug": member.slug, "error": repr(exc),
      })
      results.append(IngestRunResult(slug=..., ok=False, error=str(exc), ...))
  return BundleIngestSummary(
    bundle="uw-ios",
    members_total=len(members),
    members_ok=sum(r.ok for r in results),
    members_failed=sum(not r.ok for r in results),
    runs=results,
    duration_ms=now() - start_ts,
  )
```

### 5.2 Query flow

```
operator via MCP client:
  > palace.code.find_references(qualified_name="EvmKit.Address", project="uw-ios")

palace-mcp:
  if is_bundle("uw-ios"):                       # check Neo4j :Bundle exists
    members = bundle_members("uw-ios")
    occurrences = []
    failed_during_query = []
    for member in members:
      try:
        occs = await find_in_project(qualified_name, member.slug)
        occurrences.extend(occs)
      except Exception as exc:
        logger.warning("bundle_query_member_failed", extra={
          "bundle": "uw-ios", "slug": member.slug, "error": repr(exc),
        })
        failed_during_query.append(member.slug)
    health = compute_bundle_health(members, failed_during_query)
    return {
      "ok": True,
      "occurrences": occurrences,
      "bundle_health": health.as_dict(),
    }
  else:
    # existing single-project path unchanged; bundle_health absent
    return await find_in_project(qualified_name, project)
```

### 5.3 Bundle health computation

```python
def compute_bundle_health(
    members: list[ProjectRef],
    query_time_failures: list[str],
) -> BundleStatus:
    now_utc = datetime.now(timezone.utc)
    fresh_window = timedelta(days=7)
    stale_slugs = []
    failed_slugs = list(query_time_failures)
    fresh_count = 0
    last_full_ingest = None
    for m in members:
        last_run = get_last_ingest_run(m.slug)  # query :IngestRun nodes
        if last_run is None or last_run.status != "success":
            failed_slugs.append(m.slug)
            continue
        if now_utc - last_run.completed_at < fresh_window:
            fresh_count += 1
        else:
            stale_slugs.append(m.slug)
        if last_full_ingest is None or last_run.completed_at < last_full_ingest:
            last_full_ingest = last_run.completed_at
    return BundleStatus(
        name=...,
        members_total=len(members),
        members_fresh_within_7d=fresh_count,
        members_stale=len(stale_slugs),
        members_failed_last_ingest=len(failed_slugs),
        stale_slugs=sorted(set(stale_slugs)),
        failed_slugs=sorted(set(failed_slugs)),
        last_full_ingest_at=last_full_ingest,
    )
```

## 6. Error handling

### 6.1 Bundle ingest

- Per-member `try / except`. On exception: log `bundle_ingest_member_failed`
  with `bundle, slug, error`, append failure entry to summary. Continue
  with the next member. Outer `try` only wraps Neo4j `bundle_members`
  fetch; if that raises, the entire ingest call fails fast (no members
  to iterate).

### 6.2 Bundle query

- Per-member `try / except`. On exception: log `bundle_query_member_failed`,
  add slug to `failed_during_query`, continue. Bundle health includes the
  failed slug so the caller sees partial coverage.

### 6.3 Bundle CRUD invariants

- `register_bundle`: Cannot register the same bundle name twice.
  Constraint: `CREATE CONSTRAINT bundle_name IF NOT EXISTS FOR (b:Bundle)
  REQUIRE b.name IS UNIQUE`.
- `add_to_bundle`: Idempotent on duplicate. If `(:Bundle)-[:CONTAINS]→
  (:Project)` already exists, no-op + log `bundle_member_already_present`.
- `remove_from_bundle`: No-op + warn log if member is not present.
- `bundle_members`: Returns empty list if bundle exists but has zero
  members; raises `BundleNotFoundError` if bundle does not exist.
- Bundle name regex: `^[a-z][a-z0-9-]{1,30}$`. Validate before any Cypher
  query; reject otherwise. Closes Cypher injection vector.
- Bundle name is the human-readable identity (operator-typed). No
  separate UUID; `name` is the natural key.

### 6.4 Schema migration

- Existing `:Project` nodes without bundle membership continue to work
  through the single-project query path. No data migration needed; bundle
  is purely additive.
- Existing `palace.code.find_references(project="<single>")` queries
  follow the existing path unchanged (backward-compat).

## 7. Operator workflow

### 7.1 One-time setup

```bash
# 1. Clone all 41 repos on iMac under HS parent dir.
ssh imac-ssh.ant013.work bash -c '
  mkdir -p /Users/Shared/Ios/HorizontalSystems
  cd /Users/Shared/Ios/HorizontalSystems
  for slug in \
    unstoppable-wallet-ios EvmKit.Swift Eip20Kit.Swift MarketKit.Swift \
    HsToolKit.Swift HsCryptoKit.Swift HsExtensions.Swift ComponentKit.Swift \
    BitcoinCore.Swift BitcoinKit.Swift BitcoinCashKit.Swift LitecoinKit.Swift \
    DashKit.Swift DigiByteKit.Swift ECashKit.Swift ZcashLightClientKit \
    StellarKit.Swift TonKit.Swift TonConnectAPI TronKit.Swift \
    BinanceChainKit.Swift MoneroKit.Swift NftKit.Swift OneInchKit.Swift \
    UniswapKit.Swift HodlerKit.Swift CurrencyKit.Swift PinKit.Swift \
    LanguageKit.Swift StorageKit.Swift ThemeKit.Swift UIExtensions.Swift \
    SectionsTableView.Swift Chart.Swift HUD.Swift ActionSheet.Swift \
    ModuleKit.Swift HdWalletKit.Swift bls-swift solana-kit-ios \
    wallet-connect-swift; do
    git clone "https://github.com/horizontalsystems/$slug" "$slug" || true
  done
'
```

(Exact list of 41 should be confirmed against UW-iOS `Package.resolved`
during Phase 4.1 live smoke; the canonical authoritative list lives in
`docs/runbooks/multi-repo-spm-ingest.md`.)

### 7.2 Initial registration via MCP

```python
# Register parent mount (one-time):
palace.memory.register_parent_mount(name="hs", host_path="/Users/Shared/Ios/HorizontalSystems", container_path="/repos-hs")

# Register all 41 projects (script-driven):
palace.memory.register_project(slug="uw-ios", parent_mount="hs", relative_path="unstoppable-wallet-ios")
palace.memory.register_project(slug="evm-kit", parent_mount="hs", relative_path="EvmKit.Swift")
palace.memory.register_project(slug="eip20-kit", parent_mount="hs", relative_path="Eip20Kit.Swift")
# ... × 41

# Register bundle:
palace.memory.register_bundle(
    name="uw-ios",
    description="UW iOS app + first-party HorizontalSystems Swift Kits",
)

# Add members with tier metadata:
palace.memory.add_to_bundle(bundle="uw-ios", project="uw-ios", tier="user")
palace.memory.add_to_bundle(bundle="uw-ios", project="evm-kit", tier="first-party")
palace.memory.add_to_bundle(bundle="uw-ios", project="eip20-kit", tier="first-party")
# ... × 41
```

### 7.3 Periodic refresh

```bash
# On dev Mac after Xcode session that touches Kits:
$ ssh dev-mac
$ cd ~/Ios/HorizontalSystems
$ bash <gimle-palace>/services/palace-mcp/scripts/regen-uw-ios-scip.sh
# Script:
#   1. for each kit in 41 dirs: build + run palace-swift-scip-emit
#   2. rsync .scip files to iMac via SSH
#   3. log to ~/Library/Logs/palace-uw-ios-regen.log
#   4. notify operator on completion (terminal output)
```

```python
# In MCP client (Claude Code or any client):
palace.ingest.run_extractor(name="symbol_index_swift", bundle="uw-ios")
# Returns BundleIngestSummary; operator inspects members_failed list
# and re-ingests individual failures if needed.
```

### 7.4 Daily query usage

```python
palace.code.find_references(
    qualified_name="EvmKit.Address",
    project="uw-ios",  # bundle slug — palace expands to 41 members
)
# → {ok: true, occurrences: [...], bundle_health: {...}}
```

## 8. Acceptance criteria

1. **`:Bundle` schema** — Cypher constraint on `Bundle.name` uniqueness;
   verified by `test_register_bundle_rejects_duplicate_name`.
2. **4 new MCP tools registered** — `palace.memory.register_bundle`,
   `add_to_bundle`, `bundle_members`, `bundle_status`. Verified by
   contract test using real `streamablehttp_client` per GIM-91 wire-
   contract rule.
3. **`palace.code.find_references` bundle expansion** — `project="uw-ios"`
   slug expands to 41 member queries; results merged. Verified by
   `test_find_references_bundle_merges_per_member_results`.
4. **`palace.ingest.run_extractor` bundle iteration** — `bundle=` param
   triggers per-member ingest with failure isolation. Verified by
   `test_bundle_ingest_isolates_per_member_failures`.
5. **Per-member fail isolation** — when 1 of 41 raises, remaining 40
   complete and summary reflects 40 ok / 1 failed. Verified by
   parametrized test with synthetic failure injection.
6. **Bundle health in queries** — response includes `bundle_health`
   payload with `members_total`, `members_fresh_within_7d`,
   `members_stale`, `members_failed_last_ingest`, plus `stale_slugs` and
   `failed_slugs` lists. Verified by `test_query_response_includes_bundle_health`.
7. **`register_project` parent_mount support** — call with
   `parent_mount="hs", relative_path="EvmKit.Swift"` resolves to
   `/repos-hs/EvmKit.Swift` inside the container. Verified by
   `test_register_project_with_parent_mount`.
8. **`palace.git.*` parent_mount path resolution** — `palace.git.log
   project="evm-kit"` reads from `/repos-hs/EvmKit.Swift/.git`. Verified
   by `test_git_log_resolves_through_parent_mount`.
9. **Backward compatibility** — existing `find_references(project="<single>")`
   queries follow the original code path; `bundle_health` is absent in
   single-project responses. Verified by
   `test_find_references_single_project_unchanged`.
10. **Bundle name validation** — name regex `^[a-z][a-z0-9-]{1,30}$`;
    invalid names rejected at the Python boundary before Cypher.
    Verified by `test_bundle_name_validation`.
11. **Idempotent `add_to_bundle`** — duplicate add is a no-op. Verified
    by `test_add_to_bundle_idempotent`.
12. **3-Kit fixture passes integration test** — fixture under
    `tests/extractors/fixtures/uw-ios-bundle-mini-project/` with three
    pre-generated `.scip` files. Test creates bundle, ingests, queries,
    asserts cross-Kit reference resolution. Verified by
    `test_bundle_ingest_and_query_e2e`.
13. **Lint / format / type / test gates** — `uv run ruff check`,
    `uv run ruff format --check`, `uv run mypy src/`,
    `uv run pytest --cov=src/palace_mcp --cov-fail-under=85` all green.
14. **Per-module 90% coverage** — `pytest
    --cov=src/palace_mcp/memory/bundle --cov-fail-under=90` green.
15. **Live smoke on iMac** — operator-driven smoke per §10.4, full 41-
    member bundle indexed and queried, evidence captured with SSH-from-
    iMac shell mandate.
16. **CLAUDE.md updated** — §"Currently mounted projects" reflects HS
    parent mount + bundle workflow; §"Extractors" references new bundle
    workflow.
17. **Runbook present** — `docs/runbooks/multi-repo-spm-ingest.md`
    covers one-time setup, periodic refresh, and troubleshooting.

## 9. Verification plan

### 9.1 Pre-implementation (CX CTO Phase 1.1)

1. Confirm branch starts from `278dfcc` (post-roadmap merge).
2. Confirm `palace-swift-scip-emit` from GIM-128 supports per-project
   invocation (must be true; see
   `project_swift_emitter_strategy_2026-05-01.md`).
3. Confirm `:Project` Neo4j schema and existing `register_project`
   surface are stable (post-101a foundation).
4. Confirm `httpx.MockTransport` pattern available for client tests.

### 9.2 Per-task gates

Each implementation task ends with a green test target before the next
task starts. See implementation plan (to be authored by CX CTO in Phase
1.1, or by Board in followup).

### 9.3 Post-implementation gates

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest -q
uv run pytest --cov=src/palace_mcp --cov-fail-under=85 -q
uv run pytest --cov=src/palace_mcp/memory/bundle --cov-fail-under=90 \
  tests/memory/test_bundle.py -q
```

All must exit 0. Output pasted verbatim in CR Phase 3.1 handoff comment.

### 9.4 Live smoke (Phase 4.1, on iMac)

QA performs the procedure on iMac via SSH. Local-Mac evidence not
acceptable.

#### 9.4.1 Pre-flight

1. `ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'` —
   capture identity for evidence block.
2. Confirm GIM-128 (Swift extractor) is live in production palace-mcp
   container; Slice 4 builds on it.
3. Operator confirms 41 Kits cloned at
   `/Users/Shared/Ios/HorizontalSystems/<Kit>/`.
4. Operator generated `.scip` files via `regen-uw-ios-scip.sh` on dev
   Mac and rsynced to iMac (timestamp captured).

#### 9.4.2 Smoke procedure

```bash
set -euo pipefail

# 1. Register parent mount, projects, bundle (script-driven via MCP).
ssh imac-ssh.ant013.work \
  './services/palace-mcp/scripts/register-uw-ios-bundle.sh'  # NEW helper

# 2. Run full bundle ingest.
ssh imac-ssh.ant013.work \
  'mcp-call palace.ingest.run_extractor name=symbol_index_swift bundle=uw-ios' \
  | tee /tmp/uw-ios-ingest.json

# 3. Verify summary: 41 members, ≥ 40 ok.
jq '.members_total == 41 and .members_ok >= 40' \
  /tmp/uw-ios-ingest.json

# 4. Run cross-Kit query.
ssh imac-ssh.ant013.work \
  'mcp-call palace.code.find_references qualified_name=EvmKit.Address project=uw-ios' \
  | tee /tmp/uw-ios-query.json

# 5. Verify response shape.
jq '.bundle_health.members_total == 41 and (.occurrences | length) > 0' \
  /tmp/uw-ios-query.json

# 6. Capture failed_slugs (expected non-empty if any Kit's .scip is stale).
jq '.bundle_health.failed_slugs' /tmp/uw-ios-query.json
```

#### 9.4.3 Evidence block

PR body `## QA Evidence` must include verbatim:

```
$ ssh imac-ssh.ant013.work 'date -u; hostname; uname -a'
<output — hostname must match expected iMac>

$ jq '.members_total, .members_ok, .members_failed' /tmp/uw-ios-ingest.json
<41, 40+, 0-1>

$ jq '.bundle_health' /tmp/uw-ios-query.json
<full BundleStatus payload>

$ ssh imac-ssh.ant013.work \
    'cat ~/.paperclip/palace-mcp.log | jq -c "select(.event==\"bundle_ingest_completed\")" | tail -1'
<JSONL event with members_total / members_ok / duration_ms>
```

## 10. Out of scope (deferred)

See §2 OUT table for reactivation triggers.

## 11. Risks and mitigations

- **41 Kits regen takes too long** — `regen-uw-ios-scip.sh` may run for
  ≥ 30 min on cold builds. Mitigation: operator runs it during off-hours;
  F3 (skip-cache) deferred to followup.
- **Tantivy per-run query overhead** — bundle query iterates 41 segments
  serially. Estimated ~50 ms per segment × 41 ≈ 2 s per query. Mitigation:
  acceptable for Phase 1; F4 (single-query Tantivy) deferred.
- **Symbol grammar collisions across Kits** — two Kits may both define
  symbol `Module.Foo` if module names collide. Mitigation: SCIP module
  is per-Kit unique (`EvmKit`, `Eip20Kit`); collision unlikely in
  practice. Verified by Phase 4.1 live smoke.
- **Bundle membership drift** — operator clones a new Kit on iMac but
  forgets to call `add_to_bundle`. Mitigation: F2 (auto-discovery)
  deferred; runbook documents manual registration discipline.
- **`palace.git.*` regression** — parent_mount path resolution change
  may break existing single-project git tools. Mitigation: explicit
  regression test `test_git_log_single_project_unchanged`.
- **Backward compatibility break** — existing `register_project(slug)`
  callers without parent_mount must still work. Mitigation: `parent_mount`
  and `relative_path` are both optional; default behavior unchanged.

## 12. Rollout

1. Phase 1.1 CX CTO Formalize — verify spec + plan paths, swap any
   placeholders, reassign CX CR.
2. Phase 1.2 CX CR Plan-first review.
3. Phase 2 Implementation — TDD through plan tasks on
   `feature/GIM-182-multi-repo-spm-ingest`.
4. Phase 3.1 CX CR Mechanical — including scope audit and live-API
   curl audit (per `feedback_pe_qa_evidence_fabrication.md`).
5. Phase 3.2 CodexArchitectReviewer Adversarial — required vectors
   include Cypher injection on bundle name, per-member fail isolation,
   bundle health staleness edge cases, parent_mount path resolution
   regression for `palace.git.*`.
6. Phase 4.1 CX QA Live smoke on iMac with SSH-from-iMac evidence
   per §9.4.
7. Phase 4.2 CX CTO Merge.

## 13. Open questions

- **Exact 41-Kit canonical list** — confirmed against UW-iOS
  `Package.resolved` at Phase 4.1 live smoke; the canonical list lives
  in `docs/runbooks/multi-repo-spm-ingest.md`. If list drifts from
  Package.resolved, runbook update required.
- **Multiple parent mounts** — current spec covers one parent mount
  (`hs`). Future ThirdParty bundle (F1) needs second parent mount. Spec
  reserves the API surface (`palace.memory.register_parent_mount`)
  but does not implement multi-parent in v1.
- **`palace.memory.register_parent_mount` MCP tool surface** — is it
  needed in v1, or is parent_mount just a parameter on `register_project`?
  Defaults to "parameter only" in v1; operator decides if first-class
  parent-mount registration is worth the API surface.
