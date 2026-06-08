# Incremental Ingest with Soft-Delete (Deprecation) — Design Spec v2

**Date**: 2026-06-05 (v2.1 after second voltAgent review pass)
**Status**: Draft — awaiting user review of v2.1
**Authors**: Board (Claude main session); revisions per architect/QA/security voltAgent feedback
**Scope**: palace-mcp extractor pipeline + `bench/ingest-fresh-{build,replay}.sh` orchestration

## 0. Goal

Turn the current "rebuild-everything-or-nothing" ingest into a **fast incremental update** that runs after every code change, while preserving deleted code as soft-deleted (`:Deprecated`) nodes so historical queries still work.

Concretely:

1. After `git pull` / local commit, running `bench/ingest-fresh-replay.sh <project>` should take **30s – 5min** (not 60+ min), reflecting only what changed since last ingest.
2. Symbols and files removed from source should appear as `:Deprecated` in graph (not hard-deleted), so older queries / audit can still see them.
3. A `--force` flag should reset deprecation marks (recovery from false-positive deprecations).
4. **Safety must actually work**: threshold check must abort BEFORE writes commit (v1 spec had this broken — see §15 Review History).

## 1. Decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| Q1 | **Deprecation = `:Deprecated` label + props** (`deprecated_at`, `deprecated_in_commit`, `last_seen_in_commit`) | Soft-delete; semantic_search filters by default; audit preserved |
| Q2 | **Scope = `:Symbol + :File`** with cascade through file | Covers 99% of cases. Higher-level entities derived — not first-class |
| Q3 | **`--force` = un-deprecate all** (Cypher pre-step strips `:Deprecated` label + props) + creates `:DeprecationEvent` for audit | Recovery from buggy detector; audit trail required (v2 addition per security review) |
| Q4 | **Detection = SCIP-set diff** (post-ingest set comparison via `last_seen_in_run_id`) | Catches both file-level and in-file symbol deletions; self-contained |
| **Q5 (v2)** | **Threshold check = two-phase**: PRECHECK Cypher (count only) → Python guard → APPLY Cypher (set only) | Must abort before writes (v1 had single-statement bug — see §15) |
| **Q6 (v2)** | **Orchestrator passes `companion_run_id` explicitly to `prune_swift_symbols`** | Eliminates "find latest run" race (v1 had silent-corruption window per architect review C3) |
| **Q7 (v2)** | **Schema: `last_seen_in_run_id` scalar PROPERTY + `:LAST_SEEN_IN` relationship** (both) | Scalar for fast diff; relationship for joins to `:IngestRun` history. Architect review H1 weighed both options; chose hybrid for v1 (scalar drives the cheap MATCH; relationship gives audit join) |
| **Q8 (v2)** | **`code_ownership` does NOT filter `:Deprecated` at write-time** — filtering happens at read-time via MCP tools | Preserve "who owned the deleted code" signal — architect review H4 fix |
| **Q9 (v2)** | **Phase 4 (filter migration) split into 4a (add param, default=true) + 4b (flip default to false)** | v1's Phase 4 was silent breaking change for callers — architect M3 |

## 2. Architecture

```
bench/ingest-fresh-replay.sh <project>  [--force]
    │
    │ flock (per-project lock — single-writer guarantee, see §6/§12)
    │
    │ [--force] pre-step → MERGE :DeprecationEvent + REMOVE :Deprecated
    │
    ├── symbol_index_swift                 (MODIFY: SET last_seen_in_run_id;
    │                                       create :LAST_SEEN_IN relationship;
    │                                       REMOVE :Deprecated on revival)
    │   returns: { run_id, ok, fatal_errors, ... }
    │
    │   GATE: if not (ok and fatal_errors == 0): skip prune_swift_symbols
    │
    ├── prune_swift_symbols (NEW — takes explicit run_id from orchestrator)
    │   phase 1: PRECHECK Cypher (count stale, no writes)
    │   phase 2: Python guard (compare against threshold; abort if exceeded)
    │   phase 3: APPLY Cypher (SET :Deprecated; create :DeprecationEvent)
    │
    ├── git_history                        (already incremental via :IngestCheckpoint)
    ├── code_ownership                     (UNCHANGED at write-time;
    │                                       read-time filter added via MCP tools)
    └── embedding_symbol                    (MODIFY: skip :Deprecated symbols)
```

## 3. Components

### 3.1 NEW: `prune_swift_symbols` extractor

**Location**: `services/palace-mcp/src/palace_mcp/extractors/prune_swift_symbols/`

Files:
- `__init__.py` — package init + extractor registration
- `extractor.py` — `PruneSwiftSymbols(BaseExtractor)` class (~120 LoC)
- `cypher.py` — Cypher constants (~50 LoC)
- `subprocess_helpers.py` — hardened git invocation (~30 LoC, see §3.1.2)

**Public API**:

```python
class PruneSwiftSymbols(BaseExtractor):
    name: ClassVar[str] = "prune_swift_symbols"
    timeout_s: ClassVar[float] = 600.0
    primary_lang: ClassVar[Language] = Language.SWIFT

    async def run(
        self,
        *,
        graphiti,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        # 1. Get companion_run_id from ctx (NOT from "find latest" query)
        companion_run_id = ctx.companion_run_id
        if not companion_run_id:
            return ExtractorStats(
                ok=True,
                nodes_written=0,
                message="no companion run_id provided; skipping prune (first ingest?)",
            )

        # 2. Get head_sha via hardened subprocess
        try:
            head_sha = get_git_head_sha(ctx.repo_path)  # see §3.1.2
        except CalledProcessError as e:
            return ExtractorStats(
                ok=False,
                error_code="git_head_missing",
                message=f"git rev-parse HEAD failed in {ctx.repo_path}: {e}",
                recoverable=False,
            )

        # 3. PRECHECK Cypher (count only, no writes)
        stale_count, total_count = await _precheck_stale(
            driver, project_id=ctx.project_slug, companion_run_id=companion_run_id
        )

        # 4. Python guard
        threshold_ratio = settings.palace_prune_max_ratio  # default 0.5
        if total_count > 0 and stale_count / total_count > threshold_ratio:
            return ExtractorStats(
                ok=False,
                error_code="deprecation_threshold_exceeded",
                message=(
                    f"would deprecate {stale_count}/{total_count} "
                    f"({stale_count/total_count*100:.1f}%) > threshold "
                    f"{threshold_ratio*100:.0f}%. Use --allow-mass-deprecation to override."
                ),
                recoverable=False,
                stats={
                    "stale_count": stale_count,
                    "total_count": total_count,
                    "ratio": stale_count / total_count,
                    "threshold_ratio": threshold_ratio,
                },
            )

        # 5. APPLY Cypher (SET :Deprecated; create :DeprecationEvent)
        result = await _apply_deprecation(
            driver,
            project_id=ctx.project_slug,
            companion_run_id=companion_run_id,
            head_sha=head_sha,
            run_id=ctx.run_id,  # this prune's run_id, distinct from companion
        )

        return ExtractorStats(
            ok=True,
            nodes_written=result.deprecated_count,
            metadata={
                "deprecated_breakdown": {
                    "File": result.files,
                    "Symbol": result.symbols,
                },
                "head_commit": head_sha,
                "companion_run_id": companion_run_id,
                "deprecation_event_id": result.event_id,
                "threshold_ratio_effective": threshold_ratio,
            },
        )
```

#### 3.1.1 ExtractorRunContext addition

Extend `ExtractorRunContext` (defined in `extractors/base.py`) with:
- `companion_run_id: str | None` — for prune extractor; orchestrator sets this from preceding `symbol_index_swift.run_id`

#### 3.1.2 Hardened subprocess (`subprocess_helpers.py`)

```python
import os
import subprocess
from pathlib import Path

# Env-driven allowlist (v2.1 fix per architect N5 + security #2)
_DEFAULT_ROOTS = (
    "/Users/ant013/Ios",          # dev-mac
    "/Users/Shared/Ios",          # iMac
    "/Users/anton/Ios",           # alt iMac user
)

def _allowed_roots() -> tuple[Path, ...]:
    raw = os.environ.get(
        "PALACE_ALLOWED_REPO_ROOTS",
        ":".join(_DEFAULT_ROOTS),
    )
    return tuple(Path(r).resolve() for r in raw.split(":") if r)


def get_git_head_sha(repo_path: str) -> str:
    """Return git HEAD SHA for repo_path. SECURITY-HARDENED:

    - resolves symlinks (TOCTOU still possible on adversarial filesystems
      but accepted per §10 threat model: local trusted operator)
    - asserts path is under allowlist using Path.is_relative_to (no
      startswith-substring vulnerability, v2.1 fix per security #1)
    - uses shell=False with explicit argv
    - no PATH-relative git lookup (absolute /usr/bin/git)
    """
    GIT = "/usr/bin/git"  # absolute path; no PATH lookup

    resolved = Path(repo_path).resolve()
    allowed = _allowed_roots()
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError(
            f"repo_path {resolved} not under allowed roots: {allowed}"
        )

    result = subprocess.run(
        [GIT, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(resolved),
        shell=False,        # no shell — no command injection
        timeout=10,
        check=True,         # raises CalledProcessError on non-zero
    )
    return result.stdout.strip()
```

### 3.2 MODIFY: `symbol_index_swift`

Two MERGE templates updated (`:File` and `:Symbol`):

```cypher
MERGE (f:File {project_id: $project_id, path: $path})
ON CREATE SET f.created_at = $now
SET f.last_seen_in_run_id = $run_id,
    f.last_seen_at = $now,
    f.last_seen_in_commit = $head_sha
REMOVE f:Deprecated
REMOVE f.deprecated_at, f.deprecated_in_commit

// v2.1 fix per architect N1: replace prior :LAST_SEEN_IN edge instead of
// accumulating (one rel per node per run = unbounded growth at 250k × N/day)
WITH f
OPTIONAL MATCH (f)-[old:LAST_SEEN_IN]->()
DELETE old

WITH f
MATCH (r:IngestRun {run_id: $run_id})
MERGE (f)-[:LAST_SEEN_IN]->(r)
```

The `:LAST_SEEN_IN` relationship lets queries join to extractor metadata and commit context. Each node has at most ONE `:LAST_SEEN_IN` at any time (replaced on every UPSERT). Scalar `last_seen_in_run_id` is kept for the cheap MATCH in prune.

Estimated change: ~14 lines per Cypher template × 2 = 28 LoC.

### 3.3 NO CHANGE: `code_ownership` (write-time)

Per Q8, ownership writes proceed regardless of `:Deprecated` status. Filtering happens at READ-time in MCP tools.

This preserves the "who deleted this code" forensic signal — ownership graph remains complete even after deprecation.

### 3.4 MODIFY: `embedding_symbol`

Add `WHERE NOT s:Deprecated` to source-symbol selection in extractor's MATCH clause. Already incremental via `embedding_input_hash`; this just skips deprecated nodes for compute savings.

Estimated change: +3 LoC.

### 3.5 MODIFY: `bench/ingest-fresh-replay.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

FORCE=0
ALLOW_MASS_DEPRECATION=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        --allow-mass-deprecation) ALLOW_MASS_DEPRECATION=1; shift ;;
        ...
    esac
done

# Acquire per-project lock — single-writer guarantee (security #7)
LOCK_FILE="/var/lock/palace-ingest-${PROJECT_SLUG}.lock"
exec {LOCK_FD}>"$LOCK_FILE" || {
    echo "[error] cannot acquire lock $LOCK_FILE" >&2
    exit 1
}
if ! flock -n "$LOCK_FD"; then
    echo "[error] another ingest running for project $PROJECT_SLUG" >&2
    exit 1
}

# --force pre-step (recovery): un-deprecate all + emit audit event
if [[ $FORCE -eq 1 ]]; then
    "$VENV/bin/python" -m palace_mcp.cli.force_undeprecate \
        --project "$PROJECT_SLUG" \
        --reason "${FORCE_REASON:-operator --force flag}"
fi

# Default extractor list now includes prune_swift_symbols positioned AFTER symbol_index_swift
DEFAULT_EXTRACTORS="git_history,symbol_index_swift,prune_swift_symbols,code_ownership,embedding_symbol"

# Pass --allow-mass-deprecation through to prune extractor
if [[ $ALLOW_MASS_DEPRECATION -eq 1 ]]; then
    export PALACE_PRUNE_MAX_RATIO=1.0
fi

# Orchestrator passes companion_run_id explicitly between symbol_index_swift and prune
# (implementation: replay.py inline python builds the run-chain)
```

NEW: `palace_mcp.cli.force_undeprecate` module — real Python entrypoint (not shell-embedded one-liner). Avoids quoting hell.

Estimated change: +45 LoC (script) + +60 LoC (new CLI module).

### 3.6 MODIFY: `bench/ingest-fresh-build.sh`

```bash
FORCE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        ...
    esac
done

for kit in "${KITS[@]}"; do
    REPO_DIR=$(get_repo_dir "$kit")
    DD="$REPO_DIR/.palace-scip-derived-data"
    
    # --force OR no prior DerivedData → full rebuild
    if [[ $FORCE -eq 1 ]] || [[ ! -d "$DD" ]]; then
        rm -rf "$DD" "$REPO_DIR/.palace-scip-build"
        log "  [full rebuild] $kit"
    else
        log "  [incremental] $kit (reusing DerivedData)"
    fi
    
    # ... existing xcodebuild call (incremental by default if DD persists)
done
```

Estimated change: +12 LoC.

### 3.7 MODIFY: MCP query tools

Tools affected:
- `palace.code.semantic_search`
- `palace.code.find_references`
- `palace.code.find_owners`
- `palace.code.find_public_api`
- `palace.code.get_code_snippet`
- `palace.code.find_idiom`
- `palace.code.search_graph`
- `palace.code.query_graph` (Cypher passthrough — only documentation update)

Each gets new optional parameter `include_deprecated: bool` with Phase 4a default `True` (no behavior change), Phase 4b default flips to `False`.

Cypher addition:
```cypher
// existing match
...
WHERE ($include_deprecated OR NOT s:Deprecated)
...
```

Estimated change: ~5 LoC per tool × 7 tools = 35 LoC.

### 3.8 MODIFY: Neo4j schema

`services/palace-mcp/src/palace_mcp/memory/constraints.py`:

```cypher
// Index for fast prune MATCH
CREATE INDEX symbol_last_seen_run_idx IF NOT EXISTS
FOR (s:Symbol) ON (s.last_seen_in_run_id);

CREATE INDEX file_last_seen_run_idx IF NOT EXISTS
FOR (f:File) ON (f.last_seen_in_run_id);

// DeprecationEvent for audit (security review #4)
CREATE CONSTRAINT deprecation_event_id_uniq IF NOT EXISTS
FOR (e:DeprecationEvent) REQUIRE e.event_id IS UNIQUE;

CREATE INDEX deprecation_event_project_idx IF NOT EXISTS
FOR (e:DeprecationEvent) ON (e.project_id);
```

Estimated change: +12 LoC.

## 4. Cypher operations (canonical)

### 4.1 UPSERT with `last_seen_in_run_id` (in `symbol_index_swift`)

```cypher
MERGE (f:File {project_id: $project_id, path: $path})
ON CREATE SET f.created_at = $now
SET f.last_seen_in_run_id = $run_id,
    f.last_seen_at = $now,
    f.last_seen_in_commit = $head_sha
REMOVE f:Deprecated
REMOVE f.deprecated_at, f.deprecated_in_commit

WITH f
MATCH (r:IngestRun {run_id: $run_id})
MERGE (f)-[:LAST_SEEN_IN]->(r)
```

Same pattern applied to `:Symbol`.

### 4.2 PRECHECK_STALE (in `prune_swift_symbols`, **no writes**)

```cypher
MATCH (n:Symbol {project_id: $project_id})
WHERE n.last_seen_in_run_id IS NOT NULL
  AND n.last_seen_in_run_id <> $companion_run_id
  AND NOT n:Deprecated
WITH count(n) AS stale_symbols

MATCH (n:File {project_id: $project_id})
WHERE n.last_seen_in_run_id IS NOT NULL
  AND n.last_seen_in_run_id <> $companion_run_id
  AND NOT n:Deprecated
WITH stale_symbols, count(n) AS stale_files

MATCH (m {project_id: $project_id})
WHERE m:Symbol OR m:File
WITH stale_symbols + stale_files AS stale_total, count(m) AS overall_total
RETURN stale_total, overall_total
```

Returns counts only; Python evaluates ratio + decides.

### 4.3 APPLY_DEPRECATION (in `prune_swift_symbols`, **writes**)

v2.1 fix per architect N2: original used `CALL { … } IN TRANSACTIONS OF 5000 ROWS` followed by `WITH count(*)` which returns ONLY the LAST batch count (not total). Replaced with Python-driven batch loop + separate event-creation Cypher. This also addresses N3 (in-run race between PRECHECK and APPLY) by making batches their own transactions while accumulating count in Python.

**Phase 1 — APPLY_BATCH** (Python loops until 0 affected):

```cypher
// APPLY_BATCH — single transaction per call, LIMIT 5000
MATCH (n {project_id: $project_id})
WHERE (n:File OR n:Symbol)
  AND n.last_seen_in_run_id IS NOT NULL
  AND n.last_seen_in_run_id <> $companion_run_id
  AND NOT n:Deprecated
WITH n LIMIT 5000
SET n:Deprecated,
    n.deprecated_at = datetime(),
    n.deprecated_in_commit = $head_sha,
    n.last_seen_in_commit = COALESCE(n.last_seen_in_commit, $head_sha)
RETURN count(n) AS batch_count,
       sum(CASE WHEN n:File THEN 1 ELSE 0 END) AS batch_files,
       sum(CASE WHEN n:Symbol THEN 1 ELSE 0 END) AS batch_symbols
```

**Python loop**:

```python
total_deprecated = 0
total_files = 0
total_symbols = 0
while True:
    batch = await driver.execute_query(
        APPLY_BATCH,
        project_id=project_id,
        companion_run_id=companion_run_id,
        head_sha=head_sha,
    )
    record = batch.records[0]
    if record["batch_count"] == 0:
        break
    total_deprecated += record["batch_count"]
    total_files += record["batch_files"]
    total_symbols += record["batch_symbols"]
    if record["batch_count"] < 5000:
        break  # last partial batch
```

**Phase 2 — CREATE_DEPRECATION_EVENT** (separate Cypher, accurate count from Python):

```cypher
// CREATE_DEPRECATION_EVENT
CREATE (e:DeprecationEvent {
    event_id: randomUUID(),
    project_id: $project_id,
    action: 'deprecate',
    run_id: $run_id,
    companion_run_id: $companion_run_id,
    head_sha: $head_sha,
    deprecated_count: $total_deprecated,
    deprecated_files: $total_files,
    deprecated_symbols: $total_symbols,
    threshold_ratio_effective: $threshold_ratio_effective,  // v2.1 fix per security #5
    occurred_at: datetime()
})

WITH e
MATCH (r:IngestRun {run_id: $run_id})
MERGE (e)-[:EMITTED_BY]->(r)

RETURN e.event_id AS event_id
```

The split solves three issues simultaneously:
- N2: count is accumulated in Python — never lost to batch semantics
- N1-of-v1 (threshold ordering): each batch is its own transaction, but the Python guard already gated entry (PRECHECK ran before any APPLY_BATCH)
- security #5 (env-bypass audit): `$threshold_ratio_effective` is persisted in the event — operators with `PALACE_PRUNE_MAX_RATIO=1.0` set are visible in audit trail

### 4.4 FORCE_UN_DEPRECATE (in `palace_mcp.cli.force_undeprecate`)

v2.1 fix per architect N4: original used `collect(nodes)` which materializes the full list — OOM on projects with 100k+ deprecated nodes. Replaced with the same Python-driven batch pattern as §4.3.

**Phase 1 — COUNT_DEPRECATED** (read-only, single query):

```cypher
MATCH (n:Deprecated {project_id: $project_id})
RETURN count(n) AS un_deprecated_count
```

**Phase 2 — CREATE_FORCE_EVENT** (audit BEFORE mutation):

```cypher
CREATE (e:DeprecationEvent {
    event_id: randomUUID(),
    project_id: $project_id,
    action: 'force_undeprecate',
    reason: $reason,
    operator: $operator,  // v2.1 fix per security: sourced via pwd.getpwuid(os.geteuid()).pw_name
    un_deprecated_count: $un_deprecated_count,
    occurred_at: datetime()
})
RETURN e.event_id AS event_id
```

**Phase 3 — UN_DEPRECATE_BATCH** (Python loops until 0 affected):

```cypher
MATCH (n:Deprecated {project_id: $project_id})
WITH n LIMIT 5000
REMOVE n:Deprecated
REMOVE n.deprecated_at, n.deprecated_in_commit
RETURN count(n) AS batch_count
```

**Python loop**:

```python
import pwd, os

# Operator attribution sourced from kernel-trusted euid (v2.1 fix per security):
operator = pwd.getpwuid(os.geteuid()).pw_name  # NOT os.getenv("USER") which is spoofable

# Phase 1: count (read-only)
count_result = await driver.execute_query(COUNT_DEPRECATED, project_id=project_id)
un_deprecated_count = count_result.records[0]["un_deprecated_count"]

# Phase 2: audit event before mutation
event_result = await driver.execute_query(
    CREATE_FORCE_EVENT,
    project_id=project_id,
    reason=reason,
    operator=operator,
    un_deprecated_count=un_deprecated_count,
)
event_id = event_result.records[0]["event_id"]

# Phase 3: batched un-deprecation
confirmed = 0
while True:
    batch = await driver.execute_query(UN_DEPRECATE_BATCH, project_id=project_id)
    cnt = batch.records[0]["batch_count"]
    confirmed += cnt
    if cnt == 0 or cnt < 5000:
        break

assert confirmed == un_deprecated_count, f"audit mismatch: planned {un_deprecated_count}, actual {confirmed}"
```

### 4.5 Query filter (in MCP tools)

```cypher
// existing match clauses
...
WHERE ($include_deprecated OR NOT s:Deprecated)
...
```

Phase 4a: tool default `include_deprecated = True` → no behavior change.
Phase 4b: tool default `include_deprecated = False` → deprecated excluded.

## 5. Data flow

### 5.1 Happy path: incremental ingest

```
operator: git commit -m "delete method X"   (HEAD = abc1234)
operator: bench/ingest-fresh-replay.sh uw-ios-baseline

step 0: flock acquired                       (~0s)
step 1: xcodebuild (incremental)              (~30s, only changed files)
step 2: palace-swift-scip-emit-cli            (~10s, reads updated IndexStore)
step 3: symbol_index_swift                    (~1-2 min)
        run_id = run-2026-06-05-XYZ
        result: ok=True, fatal_errors=0
        — :File and :Symbol nodes upserted with last_seen_in_run_id=run-XYZ
        — :LAST_SEEN_IN relationships to :IngestRun
        — :Deprecated stripped from any revived nodes
        
step 3a: GATE: symbol_index_swift.ok and fatal_errors==0 → proceed to prune
         (if either fails: skip prune, log WARNING, continue with other extractors)

step 4: prune_swift_symbols                   (~1-3s)
        explicit companion_run_id=run-XYZ passed from orchestrator
        head_sha = git rev-parse HEAD (hardened subprocess) → abc1234
        
        PRECHECK: stale=1 (method X), total=300000 → ratio 0.0000033 < 0.5
        Python guard: OK
        APPLY: SET X:Deprecated; :DeprecationEvent created
        
step 5: git_history (incremental via checkpoint)  (~1-2 min)
        writes :Commit abc1234, :Author
        
step 6: code_ownership                        (~1-2 min for changed files only)
        DOES NOT filter :Deprecated (Q8) — preserves "who deleted this" signal
        
step 7: embedding_symbol                      (~30s incremental)
        WHERE NOT s:Deprecated AND embedding_input_hash != stored
        → no embedding work for deprecated X
        
step 8: flock released

total: ~60s — 5 min wall-clock
```

### 5.2 Edge cases

| Case | Behavior | Test |
|---|---|---|
| File rename (`git mv A.swift → B.swift`) | A deprecated + symbols deprecated; B + symbols created fresh. **WARN logged** if same `qualified_name` exists as both `:Deprecated` and live (signals possible rename — see §10 known limitation) | test_file_rename_warns_on_collision |
| Symbol revival (`git revert`) | MERGE in symbol_index_swift strips `:Deprecated` via UPSERT Cypher §4.1 | test_revival_un_deprecates |
| First run after Phase 1+2 migration | Legacy nodes have NO `last_seen_in_run_id` → PRECHECK and APPLY both skip them (`IS NOT NULL` guard) | test_legacy_nodes_skipped_on_first_run |
| Prune fails mid-run | `CALL { } IN TRANSACTIONS OF 5000` batches commit independently. Partial deprecation persists. Next run idempotent (already :Deprecated nodes excluded by `NOT n:Deprecated`). Audit event records partial-count | test_prune_partial_failure_idempotent |
| symbol_index_swift partially fails | Gate (step 3a) sees `ok=False or fatal_errors>0` → skip prune. WARN logged. Operator can retry or run prune alone after fixing root cause | test_skip_prune_on_symbol_index_failure |
| Concurrent ingest of same project | flock per-project blocks second invocation | test_flock_blocks_second_run |
| Mass-deprecation (misconfigured SCIP) | PRECHECK ratio > threshold → APPLY skipped, ExtractorError returned, **no writes** | test_threshold_aborts_before_writes |
| `--force` recovery | Pre-step CLI emits `:DeprecationEvent action='force_undeprecate'` with reason; THEN strips labels | test_force_creates_audit_event |
| Cross-module symbol move (extension extraction) | Old `:Symbol` deprecated, new created with different qualified_name. **Known limitation §10** — `find_references` may show stale results | (smoke test only — accepted limitation) |
| Cypher timeout | `ServiceUnavailable` → ExtractorError(`cypher_timeout`, recoverable=True). Next ingest retries | test_cypher_timeout_returns_recoverable_error |
| git rev-parse HEAD fails | Hardened subprocess raises CalledProcessError → ExtractorError(`git_head_missing`, recoverable=False) | test_git_head_missing_error |
| repo_path outside allowlist | `get_git_head_sha` raises ValueError → ExtractorError(`invalid_repo_path`, recoverable=False) | test_repo_path_outside_allowlist_rejected |

## 6. Error handling

| Failure | Detection | Response |
|---|---|---|
| **Threshold exceeded** (PRECHECK) | Python guard: `stale/total > PALACE_PRUNE_MAX_RATIO` | `ExtractorError(error_code='deprecation_threshold_exceeded', recoverable=False)` BEFORE any writes (Q5) |
| **symbol_index_swift partial failure** | Orchestrator checks `result.ok and result.fatal_errors==0` | Skip prune for this run; log WARN; emit metric |
| **`companion_run_id` not provided** (first ingest, or test) | Extractor checks `ctx.companion_run_id` | Return `ExtractorStats(ok=True, nodes_written=0, message='no companion run_id')` — graceful no-op |
| **Cypher timeout** (PRECHECK or APPLY) | `ServiceUnavailable` | `ExtractorError(error_code='cypher_timeout', recoverable=True)`. Next run retries (idempotent) |
| **Git HEAD missing / invalid path** | `subprocess_helpers.get_git_head_sha` raises | `ExtractorError(error_code='git_head_missing' or 'invalid_repo_path', recoverable=False)` |
| **`--force` Cypher fails** | shell `set -e` | Pre-step CLI exits non-zero; replay.sh aborts; nothing extractor-side touched. Audit `:DeprecationEvent` rolled back (single transaction) |
| **Concurrent ingest attempt** | `flock -n` returns non-zero | Script exits with `another ingest running` message |
| **Schema migration: wrong property type** | Property type validation in PRECHECK | Treat as missing property; WARN log; do not deprecate |

## 7. Observability

`prune_swift_symbols` returns structured stats:

```json
{
  "ok": true,
  "run_id": "run-2026-06-05-XYZ",
  "extractor": "prune_swift_symbols",
  "project": "uw-ios-baseline",
  "deprecated_count": 47,
  "deprecated_breakdown": {"File": 2, "Symbol": 45},
  "skipped_legacy_nodes": 1230,
  "head_commit": "abc1234",
  "companion_run_id": "run-2026-06-04-WWW",
  "deprecation_event_id": "uuid-of-event",
  "threshold_ratio_effective": 0.5,
  "duration_ms": 1247
}
```

`:IngestRun` audit gets:

```cypher
SET r.deprecated_count = $count,
    r.deprecated_event_id = $event_id  // NEW: link to :DeprecationEvent
```

`:DeprecationEvent` node:
- `event_id` (UUID, unique)
- `project_id`
- `action` ('deprecate' | 'force_undeprecate' | 'revive')
- `run_id` (linking back to causal :IngestRun)
- `head_sha` / `reason` / `operator` (depending on action)
- `occurred_at` (datetime)
- `deprecated_count` or `un_deprecated_count`

Audit query example — "what was deprecated in commit abc1234?":

```cypher
MATCH (e:DeprecationEvent {project_id: 'uw-ios-baseline'})
WHERE e.head_sha = 'abc1234'
MATCH (e)-[:EMITTED_BY]->(r:IngestRun)
MATCH (r)<-[:LAST_SEEN_IN]-(n)
WHERE n:Deprecated AND n.deprecated_in_commit = 'abc1234'
RETURN e.event_id, labels(n), n.qualified_name
```

Logging:
- INFO per-extractor finish
- WARNING when `skipped_legacy_nodes > 1000` (Phase 2 → Phase 3 migration not complete)
- WARNING when same `qualified_name` exists as both `:Deprecated` and live (possible file rename — see §10)
- ERROR when threshold exceeded
- ERROR when symbol_index_swift partial failure caused prune skip

## 8. Testing strategy

### 8.1 Unit tests (~12 tests)

| Test | File | Coverage |
|---|---|---|
| `test_deprecate_stale_marks_only_unchanged_nodes` | tests/extractors/prune_swift_symbols/test_cypher.py | Core deprecation logic |
| `test_specific_properties_set_correctly` | same | `deprecated_at` is datetime, `deprecated_in_commit` == passed `$head_sha`, `last_seen_in_commit` set |
| `test_revival_un_deprecates_and_strips_props` | same | UPSERT Cypher revives + strips `deprecated_at`/`deprecated_in_commit` properties (not just label) |
| `test_legacy_nodes_skipped_on_first_run` | same | `last_seen_in_run_id IS NULL` → no deprecation (Phase 2 → Phase 3 migration safety) |
| `test_precheck_returns_counts_no_writes` | same | PRECHECK Cypher computes stale_total but does NOT mutate graph |
| `test_apply_creates_deprecation_event` | same | APPLY Cypher creates `:DeprecationEvent` node + `:EMITTED_BY` relationship |
| `test_threshold_aborts_before_writes` | same | When `stale/total > threshold`, APPLY NEVER runs; graph unchanged |
| `test_force_undeprecate_clears_all_and_emits_event` | same | FORCE_UN_DEPRECATE strips labels + props AND creates `:DeprecationEvent` |
| `test_companion_run_id_none_returns_graceful_noop` | tests/extractors/prune_swift_symbols/test_extractor.py | `ctx.companion_run_id is None` → ok=True, nodes=0, message='no companion' |
| `test_git_head_missing_returns_non_recoverable_error` | same | `subprocess.CalledProcessError` → ExtractorError code='git_head_missing' |
| `test_repo_path_outside_allowlist_rejected` | tests/extractors/prune_swift_symbols/test_subprocess.py | `repo_path='/tmp/x'` → ValueError raised by `get_git_head_sha` |
| `test_subprocess_uses_shell_false_and_absolute_git` | same | `subprocess.run` called with `shell=False`, `args[0]='/usr/bin/git'` |

### 8.2 Integration tests (~10 tests, testcontainers neo4j)

| Test | Coverage |
|---|---|
| `test_full_pipeline_with_file_deletion` | Delete file via fixture, verify (a) `:File` deprecated (b) all child `:Symbol` deprecated (c) other files' symbols NOT deprecated (d) `deprecated_in_commit` matches simulated commit |
| `test_full_pipeline_with_method_deletion` | Delete one method, file survives, verify only that `:Symbol` deprecated + others in file are NOT |
| `test_revert_revives_symbols` | git revert → symbol_index_swift re-MERGEs → `:Deprecated` stripped from both label and props |
| `test_symbol_index_partial_failure_skips_prune` | Inject failure in symbol_index_swift mid-run; verify prune NOT called; original :IngestRun marked failed |
| `test_force_pre_step_creates_audit_event` | `--force` invocation via CLI; verify `:DeprecationEvent` action='force_undeprecate' with reason AND operator |
| `test_phase_2_regression_overwrites_last_seen_in_run_id` | Upsert node twice, second run_id is set; first run_id replaced (not appended) |
| `test_phase_2_to_phase_3_first_enable_no_mass_deprecation` (NEW v2.1) | Simulate Phase 2 state: ingest project with `symbol_index_swift` having written `last_seen_in_run_id=run-A`, but `prune_swift_symbols` not in extractor list. Then enable Phase 3: re-ingest with prune in list, run_id=run-B. Verify only legitimately-stale nodes deprecated, NOT all 250k (which would be mass-deprecation regression at the first Phase 3 enable). Covers the highest-risk migration transition per qa-expert v2 review |
| `test_phase_4b_explicit_include_deprecated_still_returns_deprecated` (NEW v2.1) | After Phase 4b default flip (default=False), verify that explicit `palace.code.semantic_search(include_deprecated=True)` still returns deprecated symbols. Confirms the flip doesn't break callers who explicitly opt into deprecated visibility |
| `test_last_seen_in_relationship_replaced_not_accumulated` (NEW v2.1) | Upsert node, then upsert same node with different run_id. Verify node has exactly ONE `:LAST_SEEN_IN` relationship (to the SECOND run, not both). Prevents architect N1 regression |
| `test_apply_batch_loop_accumulates_count_correctly` (NEW v2.1) | Seed 12,000 stale nodes (3 batches of 5000). Verify `:DeprecationEvent.deprecated_count` == 12000, not 2000 (last-batch). Prevents architect N2 regression |

### 8.3 MCP tool filter tests (~3 tests)

| Test | Coverage |
|---|---|
| `test_semantic_search_excludes_deprecated_by_default` (Phase 4b) | Seed live + deprecated symbol with same query relevance; assert deprecated NOT in result; assert SAME symbol returned when `include_deprecated=True` |
| `test_all_mcp_tools_accept_include_deprecated_param` (linter) | Enumerate `palace.code.*` tools via registry; assert each has `include_deprecated: bool` param. Fails CI if new tool added without param |
| `test_include_deprecated_true_returns_full_set` | Verify same symbol absent from default appears with `include_deprecated=True` |

### 8.4 Safety / failure-injection tests (~3 tests)

| Test | Coverage |
|---|---|
| `test_concurrent_replay_blocks_second_invocation` | Two `replay.sh` runs same project; second exits with "another ingest running" |
| `test_cypher_timeout_returns_recoverable_error` | Mock Neo4j driver raises `ServiceUnavailable` mid-APPLY; verify ExtractorError code='cypher_timeout', recoverable=True |
| `test_mass_deprecation_blocked_no_writes` | Seed 1000 symbols; companion_run_id mismatch causes 90% stale; PRECHECK returns counts; APPLY NEVER runs; graph unchanged |

### 8.5 Smoke (manual + CI conditional)

`tests/extractors/smoke/test_prune_uw_smoke.sh`:

1. Take fixture repo at commit X — full ingest via build.sh
2. Modify fixture (delete file, delete method) — commit X+1
3. Incremental rebuild via replay.sh (no `--force`)
4. Verify expected deprecations via cypher-shell assertions
5. `git checkout X` + incremental rebuild → expect revival
6. Assert audit trail: 2 `:DeprecationEvent` nodes (deprecate + revival)

CI integration: GitHub Actions path filter on `services/palace-mcp/src/palace_mcp/extractors/prune_swift_symbols/**` OR `bench/ingest-fresh-*.sh` triggers smoke gate.

### 8.6 Performance test

`test_prune_completes_under_5s_on_250k_symbols`:

```python
@pytest.mark.perf
@pytest.mark.skipif(not os.getenv("RUN_PERF_TESTS"), reason="opt-in")
async def test_prune_perf_at_uw_scale(neo4j_fixture):
    # Bulk seed 250k :Symbol + 25k :File via direct Cypher UNWIND
    bulk_seed_symbols(count=250_000, run_id="run-A")
    # Simulate 1% change rate
    bulk_refresh(count=247_500, run_id="run-B")
    
    start = time.monotonic()
    result = await prune(project="x", companion_run_id="run-B", head_sha="abc")
    elapsed = time.monotonic() - start
    
    # SLO: 5s on test hardware (M1 MacBook ≈ test machine)
    assert elapsed < 5.0, f"prune took {elapsed:.2f}s (SLO 5s)"
    assert result["deprecated_count"] == 2500
```

**Note**: synthetic seed uses direct Cypher UNWIND (~30s seeding overhead, NOT through `symbol_index_swift` MERGE loop). Documented in test as "measures prune Cypher path only, not full ingest". Hardware-dependent — skipped in CI by default; runs in nightly perf job.

### 8.7 Test infra

- Existing `tests/extractors/fixtures/uw-ios-mini-project/` for integration
- Testcontainers neo4j (existing)
- NEW: `tests/scip_builder.py` (~80 LoC) — programmatic SCIP gen with full symbol + occurrence support
- NEW: `tests/extractors/prune_swift_symbols/conftest.py` — uses unique `project_id="prune-test-{uuid}"` per test to avoid intra-session pollution

### 8.8 CI integration

```makefile
# services/palace-mcp/Makefile
test-prune:
	uv run pytest tests/extractors/prune_swift_symbols/ -v -m "not perf"

test-prune-perf:  ## opt-in: bench/perf workflow only
	RUN_PERF_TESTS=1 uv run pytest tests/extractors/prune_swift_symbols/ -v -m perf
```

`.github/workflows/ci.yml`:
- Existing `test` job picks up `tests/extractors/prune_swift_symbols/` via pytest discovery — no config change needed
- NEW: `smoke-prune` job triggered via path filter on prune/build/replay paths — runs `test_prune_uw_smoke.sh`

## 9. Migration plan (6 phases)

Each phase independently revertable. Phase 4 split into 4a (no behavior change) + 4b (default flip) per architect M3.

| Phase | Change | User-visible impact | Revert plan |
|---|---|---|---|
| **1** | Schema + new extractor scaffold (NOT in default list); index creation | None | Drop indexes; delete extractor files |
| **2** | `symbol_index_swift` writes `last_seen_in_run_id` + `:LAST_SEEN_IN` rel | None (just a new property) | Stop writing; legacy nodes back to no-property state |
| **3** | Enable `prune_swift_symbols` in default extractor list; orchestrator passes `companion_run_id` | Deprecation marks START appearing | Remove from default list; legacy data remains marked but no new marks |
| **4a** | Add `include_deprecated` param to MCP tools, DEFAULT TRUE (no behavior change for callers) | None | Drop param; tools revert to no-filter behavior |
| **4b** | Flip `include_deprecated` default to FALSE | Existing callers must opt into deprecated symbols | Flip back to TRUE; emit deprecation warning for tools relying on opt-out |
| **5** | `--force` flag, DerivedData persistence in build.sh, `--allow-mass-deprecation` | New CLI flags; existing flag-less invocations unchanged (incremental build kicks in when DerivedData exists) | Remove flag handling; restore unconditional `rm -rf .palace-scip-derived-data` |

Each phase blocks on tests passing for prior phase. CI gate per phase boundary.

## 10. Out of scope / Known limitations

- **Hard delete**: operator chose soft-delete. Hard delete via separate ops command (not designed here).
- **File rename detection (v1.0 limitation)**: deprecate old + create new is acceptable for v1. WARN log when same `qualified_name` lives as both `:Deprecated` and live (signals possible rename). Operator can manually `MATCH (live), (old:Deprecated) WHERE live.qualified_name = old.qualified_name CREATE (live)-[:RENAMED_FROM]->(old)` if needed. Future v1.1: integrate with `git log --follow` for rename detection.
- **Cross-module symbol moves (v1.0 limitation)**: when symbol moves from module X to Y (extension extraction), SCIP symbol-id changes — old `:Symbol` deprecated, new created with different `qualified_name`. `find_references` will show stale results from before move. Same future fix as renames.
- **Multi-project prune-in-one-pass**: one project per invocation.
- **Deprecation propagation to `:Commit`, `:Author`, `:PR`**: immutable history; not affected.
- **Authorization (v1.0 acceptance)**: local dev tool; OS-level shell access = trusted. `--force` has zero auth check beyond filesystem perms. Documented; not a future enhancement (intentional acceptance per security review #3).
- **Deprecation UI**: no palace-mcp UI exists; queries via cypher-shell or MCP tools only.
- **PII / GDPR**: no PII expected in code symbols; `:Author` GDPR handled by separate `code_ownership` retention policy (not in scope).

## 11. Effort estimate

| Phase | LoC | Effort |
|---|---|---|
| 1: schema + extractor scaffold | +180 | 2-3h |
| 2: symbol_index_swift modifications + :LAST_SEEN_IN rel | +24 | 1h |
| 3: orchestrator changes (run_id passing, gate logic) + bench script | +85 | 2-3h |
| 4a: MCP tool `include_deprecated` param (default=true) | +35 | 1h |
| 4b: flip default (separate PR after monitoring period) | +7 | 30min |
| 5: `--force` CLI module + DerivedData persistence + `--allow-mass-deprecation` | +75 | 1.5-2h |
| Tests (~22 tests) | +450 | 6-8h |
| Docs (this file + runbook + migration guide) | +80 | 1h |
| **Total** | **~936 LoC** | **~15-19h** |

(v1 spec underestimated at 9-12h per architect review L3.)

## 12. Open risks

| Risk | Mitigation |
|---|---|
| Index growth on huge projects (UW 250k symbols × multiple property indexes) | Benchmark via `test_prune_perf` SLO; per-label indexes have separate planner stats; growth bounded by project size |
| Cypher prune lock too long → blocks queries | `CALL { } IN TRANSACTIONS OF 5000 ROWS` batches commits independently |
| Operator forgets `--force` after schema change → false un-deprecations | Document in runbook; pre-step audit event records reason; revert path documented |
| `include_deprecated` param missing from new MCP tool | Linter test enumerates all `palace.code.*` tools, fails CI |
| Concurrent ingest race | flock per-project (§3.5) — single-writer guarantee |
| `--force` resurrects legit deletions (footgun per architect M2) | Operator-acknowledged. Audit event captures reason. Recovery: re-run ingest with intended SCIP to re-deprecate. Documented in runbook. |
| `PALACE_PRUNE_MAX_RATIO=1.0` env silently bypasses safety | Logged to `:DeprecationEvent.threshold_ratio_effective`; visible in audit |
| Migration Phase 2 → Phase 3 mass-deprecates legacy nodes | `IS NOT NULL` guard in PRECHECK + APPLY skips legacy. Tested by `test_legacy_nodes_skipped_on_first_run` |
| Phase 4b default flip silently changes query results for callers | Deprecation warning for one release cycle (in 4a); explicit migration note in release |
| File rename / cross-module move stale references | Documented v1.0 known limitations (§10); WARN log catches obvious cases |

## 13. Decision log

- **2026-06-05 (v1)** — Operator chose `:Deprecated` label + props over `is_active=false` field or `:Tombstone` separate node
- **2026-06-05 (v1)** — Operator chose `:Symbol + :File` scope (cascade)
- **2026-06-05 (v1)** — Operator chose SCIP-set diff over git-diff or hybrid
- **2026-06-05 (v1)** — Operator chose `--force = un-deprecate all` (recovery semantics, not full wipe)
- **2026-06-05 (v2)** — Board+architect agreed: threshold check must be two-phase (PRECHECK then APPLY) — v1 had single-statement Cypher bug. Locked as Q5.
- **2026-06-05 (v2)** — Board+architect agreed: orchestrator passes `companion_run_id` explicitly; no "find latest" lookup. Locked as Q6.
- **2026-06-05 (v2)** — Board+architect agreed: hybrid schema (scalar `last_seen_in_run_id` PLUS `:LAST_SEEN_IN` relationship). Locked as Q7.
- **2026-06-05 (v2)** — Board+architect agreed: `code_ownership` does NOT filter at write-time — read-time only. Locked as Q8.
- **2026-06-05 (v2)** — Board+architect agreed: Phase 4 split into 4a/4b. Locked as Q9.
- **2026-06-05 (v2)** — Board+security agreed: subprocess hardening via allowlist + `shell=False` + absolute git path. Implemented in §3.1.2.
- **2026-06-05 (v2)** — Board+security agreed: `:DeprecationEvent` audit trail for every deprecate/un_deprecate operation. Implemented in §3.8 + §4.3/4.4.
- **2026-06-05 (v2)** — Board+QA agreed: test suite expanded from 8 to ~22 tests covering legacy nodes, partial failures, threshold safety, file/method/method-in-file deletion edge cases.

## 14. Acceptance criteria

- [ ] Incremental ingest of small commit on uw-ios-baseline (1-5 file change) completes in < 5 min wall-clock
- [ ] `prune_swift_symbols` extractor present in registry, runs after `symbol_index_swift` by default (Phase 3 onward)
- [ ] Orchestrator passes `companion_run_id` to prune; no "find latest run" query in extractor (Q6 enforcement)
- [ ] Threshold check is two-phase (PRECHECK then APPLY); APPLY skipped if ratio exceeded; verified by `test_threshold_aborts_before_writes`
- [ ] Deleting a Swift file → its `:File` and all its `:Symbol` nodes marked `:Deprecated` with correct `deprecated_in_commit`
- [ ] Deleting a method from existing file → that method's `:Symbol` marked `:Deprecated`; siblings NOT touched
- [ ] `git revert` of deletion → `:Deprecated` automatically stripped on next ingest (label AND properties)
- [ ] `palace.code.semantic_search` Phase 4b excludes deprecated by default; Phase 4a `include_deprecated=True` default unchanged
- [ ] `palace.code.semantic_search(include_deprecated=True)` returns deprecated symbols
- [ ] `bench/ingest-fresh-replay.sh --force <project>` un-deprecates all nodes AND emits `:DeprecationEvent` action='force_undeprecate' with reason
- [ ] `bench/ingest-fresh-build.sh` reuses `.palace-scip-derived-data` between runs (xcodebuild incremental); `--force` triggers full rebuild
- [ ] No regression on full-rebuild path (existing `ingest-fresh-build.sh` without `--force` flag still works)
- [ ] flock per-project blocks concurrent invocation (verified by `test_concurrent_replay_blocks_second_invocation`)
- [ ] Subprocess invocation uses `shell=False`, absolute `/usr/bin/git`, validated `cwd`, allowlist check
- [ ] All ~22 named tests pass in CI; perf test passes in nightly job
- [ ] Smoke gate (`test_prune_uw_smoke.sh`) wired via GitHub Actions path filter, runs on every PR touching prune/build/replay

## 15. Review history

### v2 → v2.1 changes (this revision)

v2 was re-reviewed by all three voltAgents on 2026-06-05. Verdicts improved substantially:
- architect-reviewer: NEEDS_MAJOR_REVISION → **PASS_WITH_CONCERNS**
- security-auditor: HIGH_RISK_FINDINGS → **LOW_RISK**
- qa-expert: INSUFFICIENT → **NEEDS_MINOR_GAPS_CLOSED**

All v1 CRITICAL + HIGH were closed in v2, but v2 introduced new bugs of its own. v2.1 fixes them:

| Finding | v2 problem | v2.1 fix |
|---|---|---|
| **N1** (architect, HIGH): `:LAST_SEEN_IN` edge accumulation | `MERGE (f)-[:LAST_SEEN_IN]->(r)` per run → unbounded growth at 250k × N/day | §4.1: `OPTIONAL MATCH (f)-[old:LAST_SEEN_IN]->() DELETE old` before MERGE. One rel per node always |
| **N2** (architect, MEDIUM): `CALL { } IN TRANSACTIONS` returns last-batch count | `:DeprecationEvent.deprecated_count` would record only final-batch count | §4.3: split into Python-driven batch loop (APPLY_BATCH) + separate Cypher event creation. Accurate count from Python accumulator |
| **N3** (architect, MEDIUM): PRECHECK/APPLY in-run race statement | Within single connection, statements between PRECHECK + APPLY could theoretically drift | §4.3 explicitly per-batch transactions + Python guard fires once before any APPLY_BATCH |
| **N4** (architect, LOW): `force_undeprecate` `collect()` OOM risk | At 100k+ deprecated nodes, list materialization could OOM | §4.4: same Python-driven batch loop pattern as §4.3 |
| **N5** (security, MEDIUM): `threshold_ratio_effective` claimed in §12 not persisted in Cypher | Audit gap on env-bypass detection | §4.3 CREATE_DEPRECATION_EVENT now includes `threshold_ratio_effective: $threshold_ratio_effective` |
| **N6** (security, LOW): `$operator` source unspecified | Risk of `$USER` spoof | §4.4 Python source: `pwd.getpwuid(os.geteuid()).pw_name` (kernel-trusted euid) |
| **N7** (security, LOW): `startswith` substring allowlist | `/Users/ant013/Ios` matches `/Users/ant013/Ios-evil` | §3.1.2: `Path.is_relative_to()` instead of `str.startswith` |
| **N8** (security, LOW): ALLOWED_REPO_ROOTS hardcoded | New dev machine = code change + redeploy | §3.1.2: env-driven `PALACE_ALLOWED_REPO_ROOTS=...` with sane defaults |
| **N9** (qa): Phase 2→3 boundary test missing | First Phase 3 enable is highest-risk transition | §8.2: `test_phase_2_to_phase_3_first_enable_no_mass_deprecation` added |
| **N10** (qa): Phase 4a→4b default flip test missing | No verification that explicit-true callers still work after default flip | §8.2: `test_phase_4b_explicit_include_deprecated_still_returns_deprecated` added |
| **N11** (v2.1 self-add): Regression tests for N1/N2 | Without dedicated tests, future refactor could reintroduce bugs | §8.2: `test_last_seen_in_relationship_replaced_not_accumulated` + `test_apply_batch_loop_accumulates_count_correctly` |

### v1 → v2 changes

v1 of this spec was reviewed by 3 voltAgents (architect-reviewer, qa-expert, security-auditor) on 2026-06-05. All three returned blocking verdicts:

- **architect-reviewer**: NEEDS_MAJOR_REVISION — 3 CRITICAL + 5 HIGH findings
- **qa-expert**: INSUFFICIENT — 11 missing tests; multiple assertion-quality issues
- **security-auditor**: HIGH_RISK_FINDINGS — 1 HIGH + 4 MEDIUM findings

The critical findings (all fixed in v2):

| Finding | v1 problem | v2 fix |
|---|---|---|
| **C1** Threshold check post-write | Single `MATCH ... SET ... RETURN count` statement; writes commit before count returned; safety net non-functional | Q5 + §4.2/4.3 split into PRECHECK (count only) + Python guard + APPLY (set only) |
| **C2** symbol_index_swift partial failure unhandled | Prune always ran regardless of upstream success | §5.1 step 3a + §6: explicit gate on `result.ok and result.fatal_errors==0` |
| **C3** `companion_run_id` lookup race | Extractor queried "latest" — race under concurrent invocation | Q6 + §3.1.1: orchestrator passes explicit `companion_run_id` via `ExtractorRunContext` |
| **Security #6** Threshold ordering same as C1 | Identical bug found independently | Same fix as C1 |
| **H1** Schema scalar vs relationship | Property index on 250k-symbol string property + no join path to :IngestRun | Q7 + §3.2: hybrid — scalar for fast diff, relationship for joins |
| **H4** code_ownership write-time filter wrong | Lost ownership signal for deleted code | Q8 + §3.3: write-time unchanged; read-time filter in MCP tools only |
| **M3** Phase 4 silently breaks callers | "Add WHERE NOT :Deprecated" changes default results | Q9 + §9: split into 4a (param added, default=true) + 4b (default flip) |
| **Security #2** subprocess RCE | No path validation, possible shell=True | §3.1.2: hardened helper with allowlist + shell=False + absolute git path |
| **Security #4** No audit for --force | `REMOVE :Deprecated` had no audit trail | §3.8 + §4.4: `:DeprecationEvent` node for every action |
| **QA gaps (11 tests)** | Edge cases without tests, broken assertions | §8: expanded to ~22 tests covering all 11 identified gaps |

### Known v1.0 acceptable limitations (per §10)

- File renames: deprecate-old + create-new is accepted for v1; WARN log signals possible rename
- Cross-module moves: same as renames; WARN log
- `--force` footgun: operator-acknowledged; audit event captures decision

## Spec Self-Review Checklist (v2)

- [x] **Placeholder scan**: No "TBD" / "TODO" / empty sections
- [x] **Internal consistency**: Sections 2-7 align — all reference `last_seen_in_run_id`, `:Deprecated`, `prune_swift_symbols`, two-phase Cypher, `:DeprecationEvent`, explicit `companion_run_id` passing, hardened subprocess
- [x] **Scope check**: Focused on one capability (incremental + soft-delete + recovery). Multi-project, UI, hard-delete out of scope (§10)
- [x] **Ambiguity check**: 9 decisions in §1 are now locked. Edge cases enumerated in §5.2 with tests. Threshold configurable + audited. C1/C2/C3/H1/H4/M3 from v1 review explicitly addressed (§15)
- [x] **All voltAgent CRITICAL + HIGH findings closed**: C1, C2, C3, H1, H2 (acknowledged §10), H3 (acknowledged §10), H4 all addressed
- [x] **All voltAgent MEDIUM findings addressed or explicitly accepted**: M1 (last_seen_in_commit semantics — kept simple, §10 known limitation), M2 (--force footgun — accepted with audit, §10), M3 (Phase 4 split — Q9), M4 (label-disjunction planning — §4.2 split per-label MATCH), M5 (Deprecated label growth — §12 documented)
- [x] **Security HIGH finding closed**: threshold ordering bug fixed (Q5)
- [x] **QA test gaps closed**: 22 tests cover all 11 v1 gaps + edge cases
