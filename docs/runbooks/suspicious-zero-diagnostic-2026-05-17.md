# Suspicious-zero extractor diagnostic — TronKit

**Issue:** [GIM-333](/GIM/issues/GIM-333)
**Date:** 2026-05-17
**Project:** `tron-kit` (`/repos-hs/TronKit.Swift/` inside container)
**Audit report baseline:** `docs/audit-reports/2026-05-14-tron-kit-final.md`

---

## Executive summary

All 5 "suspicious zeros" from the GIM-307 TronKit audit have been diagnosed.
**No extractor has a pure logic bug** causing false-positive zero output.
Two extractors have documentation/reporting deficiencies. One has a SILENT ZERO
that should be surfaced as `MISSING_INPUT`.

| Extractor | Verdict | Three-cause | Action required |
|-----------|---------|-------------|-----------------|
| `hotspot` | VALID_EMPTY + TEMPLATE_BUG | RAN_SUCCESS_ZERO | Bug issue for misleading "scanned 0 files" template text |
| `dead_symbol_binary_surface` | CONFIG_GAP + SILENT_ZERO_BUG | RAN_SUCCESS_ZERO | Bug issue for silent MISSING_INPUT (extractor.py:263-264) |
| `public_api_surface` | CONFIG_GAP | NEVER_RAN | Commit `.palace/public-api/swift/*.swiftinterface` to TronKit |
| `cross_module_contract` | CASCADING_EMPTY | NEVER_RAN | Unblocks after `public_api_surface` CONFIG_GAP resolved |
| `cross_repo_version_skew` | CONFIG_GAP + VALID_EMPTY | RAN_SUCCESS_ZERO | Commit `Package.resolved` to TronKit; single-project has zero intra-skew by design |

**Additional finding:** The [GIM-333](/GIM/issues/GIM-333) issue description
mischaracterized `public_api_surface` ("0 symbols") and `cross_module_contract`
("0 deltas") — the actual audit report correctly lists them as BLIND SPOTS
(never ran), not as "0 findings".

---

## Step 1: Cypher inspection results

### IngestRun summary for `tron-kit` (2026-05-14 run)

Query: `MATCH (r:IngestRun {project: 'tron-kit'}) RETURN extractor, success, nodes_written ORDER BY started_at DESC`

| Extractor | success | nodes_written | error_code |
|-----------|---------|---------------|------------|
| `hotspot` | TRUE | 1613 | NULL |
| `dead_symbol_binary_surface` | TRUE | NULL (latest) / 0 | NULL |
| `cross_repo_version_skew` | TRUE | 1 | NULL |
| `public_api_surface` | — | — (no record) | — |
| `cross_module_contract` | — | — (no record) | — |

Note: `dead_symbol_binary_surface` has two IngestRun records (one from the
runner-level CREATE_INGEST_RUN and one from foundation `create_ingest_run`).

### Audit contract query results

**hotspot** (`project_id = 'project/tron-kit'`):
```cypher
MATCH (f:File {project_id: 'project/tron-kit'})
WHERE coalesce(f.hotspot_score, 0.0) > 0
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
```
→ **0 rows**. Evidence: 112 File nodes exist, 86 with hotspot data, but ALL
`hotspot_score = 0.0`. Separate check: `sum(hotspot_score) = 0.0`.

**dead_symbol_binary_surface**:
```cypher
MATCH (c:DeadSymbolCandidate {project: 'tron-kit'})
```
→ **0 rows** (no DeadSymbolCandidate nodes written).

**public_api_surface**:
```cypher
MATCH (surface:PublicApiSurface {project: 'tron-kit'}) OPTIONAL MATCH (surface)-[:EXPORTS]->(sym)
```
→ **0 surfaces, 0 symbols** (no PublicApiSurface nodes).

**cross_module_contract**:
```cypher
MATCH (d:ModuleContractDelta {project: 'tron-kit'})
```
→ **0 rows**.

**cross_repo_version_skew**:
```cypher
MATCH (p:Project {slug: 'tron-kit'})-[r:DEPENDS_ON]->(d:ExternalDependency)
WITH d.purl AS purl, collect(distinct r.resolved_version) AS versions
WHERE size(versions) > 1
```
→ **0 rows**. Evidence: 9 DEPENDS_ON edges exist, all with `resolved_version=NULL`
(no `Package.resolved` → PURLs use `@unresolved` suffix).

---

## Step 2: Code path analysis

### hotspot — `extractors/hotspot/extractor.py`

**Zero-return path:**
- Line 78-86: prerequisite check — `git_history` must have run. If not → raises
  `_HotspotError("prerequisite_missing")`. In TronKit's case, git_history DID run
  (IngestRun success=TRUE), so this check passes.
- Line 114-132: loud-fail invariants — if `file_walker` finds 0 source files, raises
  `empty_project` or `data_mismatch_zero_scan_with_files_present`. In TronKit's case,
  86 files were scanned, so this check passes.
- Line 136-141: `churn_query.fetch_churn(window_days=90)` returns 0 for ALL paths
  because ALL 20 commits predate the 90-day cutoff (last commit: 2025-08-13; run date:
  2026-05-14; cutoff: 2026-02-14).
- Line 157: `score = math.log(ccn+1) * math.log(churn+1) = math.log(ccn+1) * 0.0 = 0.0`
  for every file.
- Audit query `hotspot_score > 0` → 0 rows.
- Template line (`audit/templates/hotspot.md`): 
  ```
  scanned {{ summary_stats.get('file_count', 0) }} files, found 0 issues.
  ```
  `file_count = len(findings) = 0` — misleading because 86 files WERE scanned.
  The template conflates "files in findings" with "files scanned".

**Classification:** RAN_SUCCESS_ZERO → VALID_EMPTY (churn window exhausted for stale project)

**Bug:** Audit template `hotspot.md` reports "scanned 0 files" when `findings=[]`. It should
report the actual scanned count from a separate File node count query, not from findings length.

### dead_symbol_binary_surface — `extractors/dead_symbol_binary_surface/extractor.py`

**Zero-return path:**
- Line 258-264: `_load_periphery_findings` checks for
  `periphery/periphery-3.7.4-swiftpm.json` and `periphery/contract.json`.
  If either is absent → **returns `()` silently**.
  ```python
  if not report_path.exists() or not contract_path.exists():
      return ()
  ```
- No `MISSING_INPUT` outcome is set. No error is raised. The pipeline continues
  with an empty `periphery_findings` tuple, writes 0 nodes, finalizes with `success=True`.
- The audit report shows "found 0 dead symbol candidates" with no indication of missing inputs.

**Classification:** RAN_SUCCESS_ZERO → CONFIG_GAP (periphery fixture absent)

**Bug:** Silent zero — should return:
```python
return ExtractorStats(
    outcome=ExtractorOutcome.MISSING_INPUT,
    message="periphery fixture not found at periphery/periphery-3.7.4-swiftpm.json",
    next_action="Run periphery and commit JSON fixture to periphery/ before running this extractor",
)
```
instead of continuing silently.

### public_api_surface — `extractors/public_api_surface.py`

**Zero-return path:**
- Line 173-186: `discover_public_api_artifacts(ctx.repo_path)` looks for
  `.palace/public-api/kotlin/*.api` and `.palace/public-api/swift/*.swiftinterface`.
  If empty → returns `ExtractorStats(outcome=MISSING_INPUT, message=...)`.
- This IS the correct behavior — returns MISSING_INPUT explicitly.
- But the extractor was NEVER CALLED for TronKit, so there is no IngestRun record.
  The audit correctly shows it as a BLIND SPOT.

**Classification:** NEVER_RAN → CONFIG_GAP

**No bug** in the extractor itself. Operator needs to commit `.palace/public-api/swift/*.swiftinterface`
and then call `run_extractor(name="public_api_surface", project="tron-kit")`.

### cross_module_contract — `extractors/cross_module_contract.py`

**Zero-return path:**
- Line 229-241: `current_surfaces = surfaces_by_commit[commit_sha]` — if no
  PublicApiSurface nodes exist for the current commit → returns
  `ExtractorStats(outcome=SKIPPED, message=...)`.
- The extractor was NEVER CALLED for TronKit (no IngestRun record).
- Even if it were called, it would immediately return SKIPPED since
  `PublicApiSurface` nodes are absent (zero from Step 1).

**Classification:** NEVER_RAN → CASCADING_EMPTY (depends on public_api_surface)

**No bug.** Correct behavior. Unblocks automatically when public_api_surface CONFIG_GAP is resolved.

### cross_repo_version_skew — `extractors/cross_repo_version_skew/extractor.py`

**Zero-return path:**
- Line 205-211: if `indexed_count == 0` (no `DEPENDS_ON` data) → raises
  `DEPENDENCY_SURFACE_NOT_INDEXED` → caught at line 112-121 → returns `MISSING_INPUT`.
- In TronKit's case, dependency_surface DID run and wrote 9 DEPENDS_ON edges,
  so `indexed_count = 1` → does NOT raise. Pipeline continues.
- Line 213-218: `_compute_skew_groups(mode="project", member_slugs=["tron-kit"])`.
  The audit_contract query:
  ```cypher
  WITH d.purl AS purl, collect(distinct r.resolved_version) AS versions
  WHERE size(versions) > 1
  ```
  All 9 DEPENDS_ON edges have `resolved_version=NULL` (no `Package.resolved` →
  purl uses `@unresolved` suffix). `collect(distinct NULL) = []`, so `size([]) = 0 < 2`
  → 0 skew groups.
- Even with real resolved versions, a single-project SPM package cannot have
  intra-project version skew (single manifest, single lockfile).

**Classification:** RAN_SUCCESS_ZERO → CONFIG_GAP + VALID_EMPTY

CONFIG_GAP: `Package.resolved` is absent. Without it, all versions are `NULL/unresolved`.
VALID_EMPTY: Single-project SPM packages cannot have version skew with themselves.
The extractor is designed for bundle/multi-project scenarios. Zero is correct.

---

## Step 3: TronKit precondition verification

Location inside container: `/repos-hs/TronKit.Swift/` (host: `/Users/Shared/Ios/HorizontalSystems/TronKit.Swift/`)

| Extractor | Required artifact | Present? | Evidence |
|-----------|------------------|----------|---------|
| `hotspot` | `git_history` IngestRun (success=TRUE) | ✅ YES | IngestRun 2026-05-14 |
| `dead_symbol_binary_surface` | `periphery/periphery-3.7.4-swiftpm.json` | ❌ NO | `ls periphery/` → not found |
| `dead_symbol_binary_surface` | `periphery/contract.json` | ❌ NO | `ls periphery/` → not found |
| `public_api_surface` | `.palace/public-api/swift/*.swiftinterface` | ❌ NO | `.palace/` directory absent |
| `cross_module_contract` | `PublicApiSurface` nodes in Neo4j | ❌ NO | 0 nodes (Cypher: Step 1) |
| `cross_repo_version_skew` | `dependency_surface` IngestRun (success=TRUE) | ✅ YES | IngestRun 2026-05-14 |
| `cross_repo_version_skew` | `Package.resolved` for resolved version data | ❌ NO | `ls Package.resolved` → not found |

**TronKit project registration:** `:Project {slug: "tron-kit"}` — confirmed present in Neo4j.
**HS parent mount:** TronKit resolves via `parent_mount=hs, relative_path=TronKit.Swift`.

Note: `Package.resolved` is intentionally absent in TronKit's repo (the package resolves
dependencies dynamically). This is not a bug in TronKit — it's a common SPM practice for
libraries (vs apps which commit lockfiles).

---

## Step 4: Verdict classification

### 1. `hotspot`

| Field | Value |
|-------|-------|
| Three-cause | RAN_SUCCESS_ZERO |
| Verdict | VALID_EMPTY + TEMPLATE_BUG |
| Cypher evidence | 112 files, `sum(hotspot_score)=0.0`, all commits predate 90-day window |
| Code path | `extractor.py:157` — `log(churn+1)=0` when churn=0; `templates/hotspot.md` — "scanned 0 files" uses `len(findings)` not actual scan count |
| Precondition status | git_history: ✅ present; 90-day window: ❌ exhausted (last commit 2025-08-13) |
| Operator action | None required for data correctness. Optionally extend `PALACE_HOTSPOT_CHURN_WINDOW_DAYS` beyond 90 to cover older commits. See bug issue for template fix. |

**Why this is VALID_EMPTY:** TronKit hasn't been updated in ~9 months. All churn is zero.
Zero hotspot scores are mathematically correct. The Tornhill formula requires activity.

**Why TEMPLATE_BUG:** `hotspot.md` shows "scanned 0 files" when `findings=[]`, but 86 files
were actually processed. This is a template deficiency — misleading but not data loss.

### 2. `dead_symbol_binary_surface`

| Field | Value |
|-------|-------|
| Three-cause | RAN_SUCCESS_ZERO |
| Verdict | CONFIG_GAP + SILENT_ZERO_BUG |
| Cypher evidence | 0 DeadSymbolCandidate nodes; IngestRun success=TRUE, nodes=0 |
| Code path | `extractor.py:263-264` — silent `return ()` when periphery files absent |
| Precondition status | `periphery/periphery-3.7.4-swiftpm.json` ❌ absent; `periphery/contract.json` ❌ absent |
| Operator action | Run periphery tool and commit fixture files to TronKit repo |

**Why CONFIG_GAP:** Periphery fixture files must be pre-generated and committed.
Without them, dead symbol detection is impossible for Swift projects.

**Why SILENT_ZERO_BUG:** The extractor reports `success=True, nodes=0` without any diagnostic.
An operator running the audit sees "0 dead symbol candidates" with no indication of why,
and cannot distinguish "no dead symbols" from "periphery not run". A `MISSING_INPUT`
outcome would surface this correctly.

### 3. `public_api_surface`

| Field | Value |
|-------|-------|
| Three-cause | NEVER_RAN |
| Verdict | CONFIG_GAP |
| Cypher evidence | No IngestRun record; 0 PublicApiSurface nodes |
| Code path | `public_api_surface.py:173-186` — returns MISSING_INPUT (correct behavior) |
| Precondition status | `.palace/public-api/` ❌ absent |
| Operator action | Generate `.swiftinterface` files and commit to `.palace/public-api/swift/`; then run `run_extractor(name="public_api_surface", project="tron-kit")` |

**Note:** The [GIM-333](/GIM/issues/GIM-333) issue description says "0 symbols" for this
extractor, but the actual audit report (`2026-05-14-tron-kit-final.md`) correctly lists it
as a BLIND SPOT (never ran). There is no "0 symbols" output — there is simply no run.

### 4. `cross_module_contract`

| Field | Value |
|-------|-------|
| Three-cause | NEVER_RAN |
| Verdict | CASCADING_EMPTY |
| Cypher evidence | No IngestRun record; 0 ModuleContractDelta nodes |
| Code path | `cross_module_contract.py:229-241` — returns SKIPPED when no PublicApiSurface nodes exist |
| Precondition status | PublicApiSurface: ❌ absent (root cause: public_api_surface CONFIG_GAP) |
| Operator action | Resolve `public_api_surface` CONFIG_GAP first; then run `run_extractor(name="cross_module_contract", project="tron-kit")` |

**Note:** Same mischaracterization as public_api_surface — GIM-333 says "0 deltas" but
the audit report says "blind spot". The extractor never ran.

**Also note:** TronKit is a single-module SPM package (`Sources/TronKit/` only). Even if
run, `cross_module_contract` would likely produce 0 deltas legitimately — the extractor
tracks changes between multi-module consumers and producers, not within a single module.

### 5. `cross_repo_version_skew`

| Field | Value |
|-------|-------|
| Three-cause | RAN_SUCCESS_ZERO |
| Verdict | CONFIG_GAP + VALID_EMPTY |
| Cypher evidence | IngestRun success=TRUE, nodes=1; 9 DEPENDS_ON edges with `resolved_version=NULL`; 0 skew groups |
| Code path | `extractor.py:53-63` audit query — `collect(distinct NULL) = []`, `size([]) < 2` → 0 rows |
| Precondition status | `dependency_surface` IngestRun: ✅ present; `Package.resolved`: ❌ absent |
| Operator action | None required for correctness. If resolved version tracking needed: commit `Package.resolved` to TronKit (requires `swift package resolve`) |

**Why CONFIG_GAP:** Without `Package.resolved`, all 9 dependencies have
`resolved_version=NULL` (purl suffix `@unresolved`). Version skew computation is impossible.

**Why VALID_EMPTY:** Single-project SPM packages cannot have version skew with themselves —
the extractor's skew detection is meaningful only in bundle/multi-project contexts.
Even with a lockfile, this project would show 0 skew instances.

---

## Step 5: Bug issues

Based on this diagnostic, the following bugs require child issues:

### BUG-1: `hotspot` audit template reports "scanned 0 files" misleadingly

- **File:** `services/palace-mcp/src/palace_mcp/audit/templates/hotspot.md`
- **Current:** `scanned {{ summary_stats.get('file_count', 0) }} files` where
  `file_count = len(findings)` (always 0 when no non-zero scores)
- **Correct:** Should query actual file count processed (e.g., a supplemental Cypher
  query for `count(f:File {project_id})` similar to arch_layer supplement) or
  change the template message to accurately reflect "0 hotspot-scoring files found"
- **Child of:** [GIM-333](/GIM/issues/GIM-333)

### BUG-2: `dead_symbol_binary_surface` silently returns 0 when periphery fixtures absent

- **File:** `services/palace-mcp/src/palace_mcp/extractors/dead_symbol_binary_surface/extractor.py:263-264`
- **Current:** `return ()` when `report_path.exists()` or `contract_path.exists()` is False
- **Correct:** Should return `ExtractorStats(outcome=ExtractorOutcome.MISSING_INPUT, message=..., next_action=...)` like `public_api_surface` does at line 175-186
- **Child of:** [GIM-333](/GIM/issues/GIM-333)

---

## Step 6: GIM-307 audit report Known Limitations update

See below for the update appended to `docs/audit-reports/2026-05-14-tron-kit-final.md`.

The following three findings in the 2026-05-14 TronKit final audit report have been
diagnosed as CONFIG_GAP / VALID_EMPTY and should NOT be interpreted as
"clean" results:

- **hotspot "scanned 0 files"** → All commits predate the 90-day churn window.
  Legitimate zero, but misleading template text. See BUG-1.
- **dead_symbol_binary_surface "0 candidates"** → Periphery fixture files absent.
  Silent CONFIG_GAP. See BUG-2.
- **cross_repo_version_skew "0 instances"** → No `Package.resolved`.
  All resolved_versions are NULL; skew cannot be computed.

The following two were correctly shown as blind spots (not zeros):
- **public_api_surface** → BLIND SPOT. Need `.palace/public-api/swift/*.swiftinterface`.
- **cross_module_contract** → BLIND SPOT. Cascades from public_api_surface.

---

## Deferred

Empirical re-verification by running these extractors on a reference project with
known non-zero output requires the VirtioFS fix (IB-2 from [GIM-332](/GIM/issues/GIM-332)).
This diagnostic is based on Neo4j inspection + code analysis, which is sufficient to
classify all 5 extractors without running new extractor calls.
