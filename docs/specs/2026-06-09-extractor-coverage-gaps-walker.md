# Extractor coverage gaps — walker spec (2026-06-09)

**Generated:** 2026-06-09 by Board, after full sweep `palace_project_analyze
depth=full force_new=true` on 12 UW iOS kits + uw-ios-baseline.

## Context

Per Board run on 2026-06-09 05:32-05:55 UTC: 13 projects launched with full
profile (19 extractors each). 12 returned `SUCCEEDED_WITH_FAILURES`,
uw-ios-baseline got stuck and was resumed. Per-extractor Neo4j label-count
verification surfaced **11 distinct defects** ranging from CRITICAL silent
no-ops (extractor returns OK but writes 0 data) to MISSING_INPUT blockers
needing pre-generated fixtures.

This is the walker spec to fix them all sequentially.

## Discovery summary (Neo4j counts per kit)

| Extractor | Wrote real data? |
|---|---|
| `symbol_index_swift` | ✅ 219 – 49,552 symbols per kit |
| `embedding_symbol` | ✅ 100% symbol coverage |
| `arch_layer` | ⚠️ partial — :Module yes, :Layer = 0, :ArchRule = 0 ALL kits |
| `crypto_domain_model` | ✅ 0-4 :CryptoFinding |
| `localization_accessibility` | ✅ :HardcodedString + :A11yMissing |
| `error_handling_policy` | ✅ :ErrorFinding + :CatchSite |
| `dependency_surface` | ✅ :ExternalDependency 0-8 |
| `testability_di` | ✅ :DiPattern + :UntestableSite |
| `hotspot` | ✅ :Function |
| `prune_swift_symbols` | ✅ |
| **`coding_convention`** | ❌ **SILENT** — OK status, 0 :Convention / :ConventionViolation ALL kits |
| **`reactive_dependency_tracer`** | ❌ **SILENT** — OK status, 0 :ReactiveComponent ALL kits |
| **`git_history`** | ⚠️ undercount — 1-2 :Commit per kit (should be hundreds) |
| `dead_symbol_binary_surface` | ❌ RUN_FAILED — periphery fixtures missing |
| `public_api_surface` | ❌ MISSING_INPUT — no `.palace/public-api/swift/*.swiftinterface` |
| `cross_module_contract` | ❌ SKIPPED — depends on public_api_surface |
| `cross_repo_version_skew` | ❌ MISSING_INPUT — claims "no DEPENDS_ON" despite dependency_surface OK |
| `hot_path_profiler` | ❌ MISSING_INPUT — no `profiles/` dir |

## Walker scope

This is a **walker root**. CXCTO opens children **one at a time**,
sequentially in the order below. Each child follows the standard slice
protocol: PE drafts plan + opens PR → CXCodeReviewer (Phase 3.1) →
OpusArchitectReviewer (Phase 3.2) → CXCTO gate → CXQAEngineer smoke → CXCTO
autonomous-merge when CI green per `feedback-autonomous-merge-when-ci-green`.

CX-team-1-task rule is in force: only one walker child active at any time.

After each child merges, Board reruns the per-defect re-verification
(re-running per-kit Neo4j counts and confirming the missing nodes now exist).

## Sequencing rationale

- **DEFECT-1 + DEFECT-2** are silent no-ops — extractor lies about success.
  Highest severity (data integrity). Fix first.
- **DEFECT-3** (arch_layer-Layer-gap) is partial implementation — fix while
  arch_layer code is hot in the engineer's head.
- **DEFECT-4** (git_history undercount) — different sub-system, can come next.
- **DEFECT-5 + DEFECT-6** (periphery + public_api fixtures) — tooling/CI work
  to generate per-kit artifacts; gated on operator approval for CI cost.
- **DEFECT-7** (cross_repo_version_skew false MISSING_INPUT) — pure logic
  fix in the gate check.
- **DEFECT-8** (cross_module_contract auto-unblock) — depends on DEFECT-6.
- **DEFECT-9** (hot_path_profiler graceful skip) — make it MISSING_INPUT
  with helpful message but mark as expected-empty for kits with no profiles.
- **DEFECT-10** (Tantivy LockBusy on concurrent git_history) — orthogonal
  concurrency fix.
- **DEFECT-11** (project_analyze stuck-RUNNING) — orthogonal lease-recovery
  fix.

---

## DEFECT-1 — `coding_convention` silent no-op (status=OK, 0 nodes written)

**Symptom**

```
checkpoint.coding_convention: OK
ingest_run_id=ab9bb291-be1c-449a-8bbf-3eb2590647f3
```

Neo4j: `MATCH (c:Convention) WHERE c.project_id='project/evm-kit' RETURN
count(c)` → **0**. Same on all 12 kits.

Audit report claimed `coding_convention` ran but zero `:Convention` and
`:ConventionViolation` nodes were ever written. This is the most insidious
class of failure: the operator believes coverage exists when it does not.

**Files (PE to confirm via codebase-memory)**

- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/` (likely
  path; PE confirms exact module).

**Fix approach (PE proposes)**

PE reads the extractor source, runs it manually on a single kit, and
identifies why it never reaches the write phase. Two likely root causes:

1. Empty result set treated as "no findings" → returns OK without writing
   any "empty-report" sentinel. Need at least a `:Convention {
   project_id, profile_run_id }` summary node so the operator can tell the
   extractor RAN vs. has-no-data.
2. Cypher write path silently fails (wrong constraint, missing label,
   etc.) — logger.error not surfaced through the checkpoint contract.

PE picks one of:
- (a) Write a `:Convention {summary=true, project_id, run_id, scanned_files}`
  sentinel even when the analyzer returns 0 violations.
- (b) Fix the write path so violations land in Neo4j AND add the sentinel.

PE picks (b) if the analyzer is producing data but write is broken;
otherwise (a).

**Acceptance**

- After fix, every successful `coding_convention` run leaves at least one
  `:Convention` summary node in Neo4j with `project_id` and `ingest_run_id`.
- For kits with real conventions (Swift uses CamelCase, etc.) at least one
  `:Convention` data node is present.
- Unit test covers "OK status implies ≥1 :Convention summary node".

**Board re-verification**

```bash
cypher-shell ... "MATCH (c:Convention) WHERE c.project_id='project/evm-kit'
RETURN count(c) AS conv;"
# Expect: ≥ 1
```

---

## DEFECT-2 — `reactive_dependency_tracer` silent no-op

**Symptom**

```
checkpoint.reactive_dependency_tracer: OK
ingest_run_id=10ad8277-...
```

Neo4j: `MATCH (r:ReactiveComponent) WHERE r.project_id='project/evm-kit'
RETURN count(r)` → **0** on all 12 kits.

Same class as DEFECT-1: extractor claims success, writes nothing.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/`

**Fix approach (PE proposes)**

Same template as DEFECT-1:

1. Examine the extractor. If it expects pre-generated reactive facts
   (.json under `reactive/`), this is MISSING_INPUT not OK — re-classify.
2. If it parses Swift Combine/RxSwift directly, the parser is silently
   producing 0 components — debug that.
3. Add a `:ReactiveComponent {summary=true}` sentinel guaranteeing
   `OK ⇒ ≥ 1 node`.

**Acceptance**

- ≥ 1 `:ReactiveComponent` (or sentinel) per project after a successful run.
- For UW iOS app: substantial reactive code (Combine `@Published`,
  `ObservableObject`) → real components found.

**Board re-verification**

```bash
cypher-shell ... "MATCH (r:ReactiveComponent) WHERE r.project_id='project/evm-kit'
RETURN count(r);"
# Expect: ≥ 1
```

---

## DEFECT-3 — `arch_layer` writes `:Module` but not `:Layer` / `:ArchRule`

**Symptom**

- `:Module` ✅ 1-4 per kit
- `:Layer` ❌ **0** on ALL 12 kits
- `:ArchRule` ❌ **0**
- `:ArchViolation` ❌ **0**

The extractor partially completes — module DAG nodes land — but layer
rules and violations never materialize.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/`

**Fix approach (PE proposes)**

Two paths:

1. Layer rules require a config file under `.palace/arch_layer.yaml`
   declaring layer names + allowed/forbidden imports. If missing, the
   extractor should skip layer evaluation but still create a `:Layer
   {summary=true, status="config_missing"}` sentinel.
2. Layer rules are inferred from module naming heuristics (Core/UI/Net/...).
   If extractor doesn't run the heuristic, add it as a fallback.

PE picks (1) if the project supports config files; (2) for general use.
Recommended: implement (2) so every kit gets at least heuristic layers
without per-project config burden.

**Acceptance**

- ≥ 1 `:Layer` per kit after run.
- Documentation explains how operators can override defaults with
  `.palace/arch_layer.yaml` if needed.

**Board re-verification**

```bash
cypher-shell ... "MATCH (l:Layer) WHERE l.project_id='project/evm-kit'
RETURN l.name, l.kind;"
# Expect: multiple rows
```

---

## DEFECT-4 — `git_history` writes only 1-2 commits per kit

**Symptom**

- `:Commit` count per kit = 1-2 (monero-kit has 2, all others have 1).
- Each kit has hundreds of commits in real git history; not all need to
  land but 1-2 is clearly truncated.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/git_history/`

**Fix approach (PE proposes)**

Examine the extractor's commit walker:

1. It may be walking only HEAD and not following parents.
2. It may have a `max_commits` config defaulting to 1.
3. It may be filtering commits by author/date and the filter is too
   strict.

PE identifies the actual cause via git_history source + run trace.

**Acceptance**

- After fix, per-kit `:Commit` count reflects real recent history
  (default: last 500 commits or last 12 months, whichever smaller).
- Operators can opt-in to full history via a config flag.

**Board re-verification**

```bash
cypher-shell ... "MATCH (c:Commit) WHERE c.group_id='project/evm-kit'
RETURN count(c);"
# Expect: ≥ 50 (or whatever the default cap is)
```

---

## DEFECT-5 — `dead_symbol_binary_surface` RUN_FAILED (periphery fixtures missing)

**Symptom**

```
RUN_FAILED
error_code=periphery_fixtures_missing
message=periphery fixture not found:
/Users/ant013/Ios/uw-fresh-2026-06-04/EvmKit.Swift/periphery/periphery-3.7.4-swiftpm.json
```

All 12 kits hit the same path. The extractor expects pre-generated
Periphery JSON committed under `<repo>/periphery/`.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/dead_symbol_binary_surface/`
- (new) `bench/regen-periphery.sh` — script to run Periphery on each kit
  and write the JSON.

**Fix approach (PE proposes)**

1. Add a `bench/regen-periphery.sh <kit>` (or extend existing
   `bench/ingest-fresh-build.sh`) that runs:

   ```bash
   periphery scan --workspace Wallet.xcworkspace --schemes <scheme> \
     --format json > <repo>/periphery/periphery-3.7.4-swiftpm.json
   ```

2. Document the script in `docs/runbooks/regen-periphery.md`.
3. Run the script for each kit to populate fixtures.
4. Re-run `palace_project_analyze` to confirm `dead_symbol_binary_surface`
   now returns OK.

Note: Periphery requires xcodebuild — same pre-flight as DEFECT-2 in the
prior walker (UW iOS requires `Config.xcconfig`; here too).

**Acceptance**

- `bench/regen-periphery.sh` works for at least 3 kits (small set).
- After regen, `:DeadFinding` count > 0 for at least 1 kit.
- Documentation explains how to refresh fixtures after source changes.

**Board re-verification**

```bash
bash bench/regen-periphery.sh evm-kit
palace.project.analyze slug=evm-kit extractors=["dead_symbol_binary_surface"] force_new=true
cypher-shell ... "MATCH (d:DeadFinding) WHERE d.group_id='project/evm-kit' RETURN count(d);"
# Expect: > 0
```

---

## DEFECT-6 — `public_api_surface` MISSING_INPUT (no .swiftinterface artifacts)

**Symptom**

```
MISSING_INPUT
message=No public API artifacts found under '.palace/public-api/kotlin/*.api'
or '.palace/public-api/swift/*.swiftinterface'.
```

All 12 kits hit this. Without `public_api_surface`, the downstream
`cross_module_contract` is also blocked (DEFECT-8).

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/public_api_surface/`
- (new) `bench/regen-public-api.sh`.

**Fix approach (PE proposes)**

1. Add `bench/regen-public-api.sh` that uses `swift build
   -emit-module-interface-path` (or xcodebuild equivalent) to write
   `.swiftinterface` files into `<repo>/.palace/public-api/swift/`.
2. Document in runbook.
3. Run for each kit.

**Acceptance**

- `bench/regen-public-api.sh evm-kit` writes ≥ 1 `.swiftinterface` to
  `EvmKit.Swift/.palace/public-api/swift/`.
- After regen, `:PublicApiSurface` count > 0 for evm-kit.
- DEFECT-8 (cross_module_contract) unblocks automatically.

**Board re-verification**

```bash
bash bench/regen-public-api.sh evm-kit
palace.project.analyze slug=evm-kit extractors=["public_api_surface"] force_new=true
cypher-shell ... "MATCH (p:PublicApiSurface) WHERE p.group_id='project/evm-kit' RETURN count(p);"
# Expect: > 0
```

---

## DEFECT-7 — `cross_repo_version_skew` falsely reports MISSING_INPUT

**Symptom**

```
MISSING_INPUT
message=all targets lack :DEPENDS_ON data; run dependency_surface first
```

But `dependency_surface` ALREADY ran successfully in the same chain (OK
status, wrote `:ExternalDependency` 1-8 per kit). The gate is wrong.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/`

**Fix approach (PE proposes)**

PE reads the gate check. Two likely bugs:

1. The query looks for `:DEPENDS_ON` relationships from `:Module` →
   `:ExternalDependency`, but `dependency_surface` may write differently
   (e.g., `:Project -[:DEPENDS_ON]-> :ExternalDependency`).
2. The query has a project filter that's not matching `project_id`
   vs. `group_id`.

PE fixes the gate to recognize the data shape actually written.

**Acceptance**

- After fix, `cross_repo_version_skew` returns OK (not MISSING_INPUT) on
  every kit where `dependency_surface` succeeded.
- If real skews exist (e.g., Alamofire 5.x vs. 4.x between kits), at
  least one `:VersionSkew` finding is recorded.

**Board re-verification**

```bash
palace.project.analyze slug=evm-kit extractors=["dependency_surface","cross_repo_version_skew"] force_new=true
# Expect both OK
```

---

## DEFECT-8 — `cross_module_contract` SKIPPED because of DEFECT-6

**Symptom**

```
SKIPPED
message=No PublicApiSurface/PublicApiSymbol rows found for the current commit '...'.
```

This is downstream of DEFECT-6. Once DEFECT-6 fixes public_api_surface,
this should auto-unblock.

**Fix approach**

No code change needed beyond DEFECT-6. Verify post-DEFECT-6 that
`cross_module_contract` returns OK and writes `:ModuleContractDelta` /
`:ModuleContractSnapshot`.

**Acceptance**

- After DEFECT-6 lands, `cross_module_contract` returns OK on at least 1
  kit (evm-kit) and writes `≥ 1 :ModuleContractSnapshot`.

**Board re-verification**

```bash
cypher-shell ... "MATCH (s:ModuleContractSnapshot) WHERE s.group_id='project/evm-kit' RETURN count(s);"
# Expect: > 0
```

---

## DEFECT-9 — `hot_path_profiler` should not block status

**Symptom**

```
MISSING_INPUT
message=profiles directory not found under repo root:
/Users/ant013/Ios/uw-fresh-2026-06-04/EvmKit.Swift/profiles
```

Unlike DEFECT-5 + DEFECT-6 (which need fixture-generation tooling),
runtime traces require actual Instruments runs against the iOS app
hardware. Kits don't really need this — it's app-level data.

**Fix approach (PE proposes)**

Re-classify the absence as `NOT_APPLICABLE` for projects without an
expected `profiles/` directory (most kits). Keep MISSING_INPUT for
projects where profiles ARE expected (UW iOS app, baseline) but missing.

Add `expected_profile=true` flag on `:Project` for projects that should
have profiles. Default false for kits.

**Acceptance**

- For evm-kit: `hot_path_profiler` returns `NOT_APPLICABLE` (not
  MISSING_INPUT).
- For uw-ios-app / uw-ios-baseline: returns MISSING_INPUT with actionable
  next_action.

**Board re-verification**

```bash
palace.project.analyze slug=evm-kit extractors=["hot_path_profiler"] force_new=true
# Expect: outcome=NOT_APPLICABLE
palace.project.analyze slug=uw-ios-baseline extractors=["hot_path_profiler"] force_new=true
# Expect: outcome=MISSING_INPUT with actionable message
```

---

## DEFECT-10 — `git_history` LockBusy on concurrent runs

**Symptom**

```
RUN_FAILED
error_code=unknown
message=ValueError: Failed to acquire Lockfile: LockBusy. Some("Failed
to acquire index lock. If you are using a regular directory, this means
there is already an `IndexWriter` working on this `Directory`, in this proces"
```

When 13 projects ran `git_history` concurrently, 2 (hd-wallet-kit,
hs-crypto) failed on Tantivy lock contention. Tantivy doesn't support
concurrent writers from multiple processes (or even multiple async tasks
in same process if both grab `IndexWriter`).

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/git_history/`
- The Tantivy index location (likely shared) used by git_history.

**Fix approach (PE proposes)**

1. **Easy:** retry-with-backoff on LockBusy (3 retries, 2s/4s/8s).
2. **Better:** project-level Tantivy index (one writer per project, no
   contention).
3. **Best:** in-process semaphore that serializes `IndexWriter` access
   across all concurrent git_history runs.

PE picks (1) for fast fix; layer (3) on top if (1) proves insufficient.

**Acceptance**

- 13 concurrent `palace.project.analyze` with `git_history` in the chain
  → all 13 git_history checkpoints return OK (or SKIPPED), zero
  LockBusy failures.

**Board re-verification**

Re-run the full sweep (the same 13 parallel calls as today) and observe
0 LockBusy failures.

---

## DEFECT-11 — `palace.project.analyze` can get stuck in status=RUNNING with all checkpoints NOT_ATTEMPTED

**Symptom**

uw-ios-baseline run `854607d4-e400-4cf4-88d2-c1668b55f499` was started at
05:33:01, marked status=RUNNING. By 05:55:20 (22 minutes later), all 19
checkpoints still NOT_ATTEMPTED, `lease_owner=null` (lease expired),
`lease_expires_at=null`. The run is dead but blocks new launches with
`ACTIVE_ANALYSIS_RUN_EXISTS`.

`analyze_resume` does relaunch background_execution_scheduled=true but
the run state doesn't reset properly — the underlying background task
that should drive checkpoints never started OR died silently.

**Files**

- `services/palace-mcp/src/palace_mcp/project_analyze.py` (the
  background execution scheduler).
- The lease-recovery code path.

**Fix approach (PE proposes)**

1. When lease expires AND status=RUNNING, treat the run as dead-stuck
   and surface this via `palace.project.analyze_status` as
   `STUCK_NEEDS_RECOVERY` instead of `RUNNING`.
2. `palace.project.analyze_resume` for a stuck run should reset the
   first NOT_ATTEMPTED checkpoint to start fresh AND actually start the
   background execution (not just schedule).
3. Add a `--force-restart` option to `palace.project.analyze` that
   atomically cancels a stuck run and starts fresh.

**Acceptance**

- A stuck run becomes resumable without manual Cypher intervention.
- `palace.project.analyze` with `force_new=true` on a stuck run cancels
  the stuck run and starts a fresh one (instead of erroring with
  ACTIVE_ANALYSIS_RUN_EXISTS).

**Board re-verification**

Synthesize a stuck-run scenario in test, verify recovery API works.

---

## Walker sequencing

CXCTO opens children one-by-one in this order:

1. **DEFECT-1** — `coding_convention` silent no-op
2. **DEFECT-2** — `reactive_dependency_tracer` silent no-op
3. **DEFECT-3** — `arch_layer` partial (:Layer/:ArchRule = 0)
4. **DEFECT-4** — `git_history` undercount (1-2 commits)
5. **DEFECT-7** — `cross_repo_version_skew` false MISSING_INPUT (pure
   logic fix, fast)
6. **DEFECT-11** — `project_analyze` stuck-run recovery (infra
   reliability, helps subsequent verification)
7. **DEFECT-10** — `git_history` LockBusy concurrency
8. **DEFECT-9** — `hot_path_profiler` NOT_APPLICABLE classification
9. **DEFECT-5** — `bench/regen-periphery.sh` + fixture generation
10. **DEFECT-6** — `bench/regen-public-api.sh` + fixture generation
11. **DEFECT-8** — auto-verify after DEFECT-6 lands

After each child merges, Board reruns the per-extractor count query and
confirms the missing nodes now exist.

CX-team-1-task rule (memory `feedback-one-cx-agent-one-task`): only one
child active at a time across the entire CX team. CTO closes one child
completely (merged + Board re-verified) before opening the next.
