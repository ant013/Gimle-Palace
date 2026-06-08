# Palace-MCP post-merge verification fixes — walker spec

**Generated:** 2026-06-08 by Board, after end-to-end verification of develop
features (GIM-1491 / GIM-1497 / GIM-1500 / GIM-1519 / 3 extractor fixes) on
native MacBook environment with `uw-ios-baseline`, `evm-kit`, and version/0.49
checkouts.

## Context

After merging GIM-1491+1497 (incremental ingest + soft-delete), GIM-1500
(namespace resolver), GIM-1519 (native passthrough unification, 8 phases),
and 3 extractor fixes (PR #400), Board performed exhaustive verification on
the native MacBook stack. The verification surfaced **6 concrete defects**
that block real-world usage of the new features on native deployment.

Verification matrix:

- Layer 0 — health: ✅ (palace-mcp had to be manually restarted to pick up
  develop-merged code — see DEFECT-6)
- Layer 1 — GIM-1491/1497: ✅ substrate works (body_hash skip 194× speedup,
  `last_seen_in_run_id` written, prune deprecated 1 orphan), but **2 bugs in
  skip-path semantics** — see DEFECT-3 + DEFECT-4
- Layer 2 — GIM-1500: ✅ after restart
- Layer 3 — GIM-1519: ✅ 6/6 native dispatch, but 2 tools (`detect_changes`,
  `get_code_snippet`) hardcode Docker mount paths — see DEFECT-5
- Layer 4 — 3 extractor fixes: ✅ all confirmed (hotspot lizard exec,
  dead_code 0-edge guard, CM bridge regex)
- Bonus — UW iOS 0.49 fresh SCIP build via `bench/ingest-fresh-build.sh`:
  ❌ blocked by 2 script defects — DEFECT-1 + DEFECT-2

## Walker scope

This is a **walker root**. CXCTO opens children **one at a time**, sequentially:
DEFECT-1 → DEFECT-2 → DEFECT-3 → DEFECT-4 → DEFECT-5 → DEFECT-6.

Each child follows standard slice protocol:
1. PE/MCPEngineer drafts plan + opens PR
2. CXCodeReviewer phase 3.1 (with `gh pr checks` paste)
3. OpusArchitectReviewer phase 3.2
4. CXCTO gate (verifies plan-implementation parity)
5. CXQAEngineer smoke + qa-evidence
6. CXCTO autonomous-merge when CI green (per
   `feedback-autonomous-merge-when-ci-green`)

CX-team-1-task rule is in force: only one walker child active at any time.

After each child merges, **Board reruns the verification test** for that
specific defect (instructions below per defect).

## Acceptance criteria (walker-level)

- All 6 child issues merged to develop
- Board re-verification passes for all 6 defects on native MacBook
- No regression in already-working features (Layer 0/1/2/3/4 still pass after
  changes)

---

## DEFECT-1 — bench/ingest-fresh-build.sh hardcodes scheme `UnstoppableWallet`

**Symptom**

```
xcodebuild: error: The workspace named "Wallet" does not contain a scheme
named "UnstoppableWallet". The "-list" option can be used to find the names
of the schemes in the workspace.
```

Script line 33 declares `unstoppable-wallet-ios|UnstoppableWallet|...`,
but on `version/0.49` the schemes are `Production` / `Development` (UW iOS
renamed scheme upstream).

**Files**

- `bench/ingest-fresh-build.sh` — line 33 (ALL_KITS array)

**Fix approach (PE proposes)**

Either:
- Add `SCHEME_OVERRIDE` env var → `${SCHEME_OVERRIDE:-UnstoppableWallet}`
- Or: detect scheme via `xcodebuild -workspace Wallet.xcworkspace -list` and
  prefer `Production` → `Development` → `UnstoppableWallet` in that order

PE picks the approach in the slice plan (justify with 2-3 sentences).

**Acceptance**

- `bench/ingest-fresh-build.sh unstoppable-wallet-ios` resolves the scheme
  automatically on UW iOS `version/0.49` (no `xcodebuild: error: scheme not
  found`).
- Unit test or smoke check covers the resolution logic.

**Board re-verification**

```bash
cd /Users/ant013/Ios/uw-fresh-2026-06-04/unstoppable-wallet-ios && \
  git fetch origin version/0.49 && git checkout origin/version/0.49 && \
  /Users/ant013/Android/Gimle-Palace/bench/ingest-fresh-build.sh unstoppable-wallet-ios
# Expected: [resolve] step succeeds (proceeds to [build] step), no "scheme
# not found" error
```

(DEFECT-2 will still block [build] step but [resolve] should succeed.)

---

## DEFECT-2 — bench/ingest-fresh-build.sh fails on missing Config.xcconfig

**Symptom**

```
.../Configuration/App/App-Dev.xcconfig:1:1: error: could not find included
file '../Config.xcconfig' in search paths (in target 'App' from project
'Unstoppable')
```

`Config.xcconfig` is private (gitignored) and not provisioned by the bench
script. UW iOS expects it to exist with API keys / signing identifiers.

**Files**

- `bench/ingest-fresh-build.sh` — the [build] step (lines 95-114)

**Fix approach (PE proposes)**

Either:
- Provision a placeholder `Config.xcconfig` with sentinel values
  (`API_KEY=PLACEHOLDER\nBUNDLE_ID=com.example.placeholder`) before the
  [build] step
- Or: document where to obtain real Config.xcconfig and exit early with a
  clear error message + path-to-fix
- Or: skip Config.xcconfig dependency by passing
  `-xcconfig /dev/null` (if xcodebuild allows)

PE picks the approach. Recommended: placeholder file pattern, because the
script already patches GRDB inline (precedent).

**Acceptance**

- `bench/ingest-fresh-build.sh unstoppable-wallet-ios` succeeds the [build]
  step on a clean checkout without operator setup, OR exits with a
  human-readable error explaining exactly what's missing and where to get
  it.
- Documentation (`docs/runbooks/uw-ios-baseline-first-ingest.md` or similar)
  updated.

**Board re-verification**

```bash
/Users/ant013/Android/Gimle-Palace/bench/ingest-fresh-build.sh unstoppable-wallet-ios
# Expected: [build] step proceeds OR fails with clear actionable message
```

---

## DEFECT-3 — GIM-1491 skip path does not update last_seen_in_run_id

**Symptom**

When `symbol_index_swift` returns `outcome=SKIPPED` (body_hash match,
nothing changed), it calls `finalize_ingest_run(success=True)` but does NOT
update `last_seen_in_run_id` on existing :File nodes. Subsequent
`prune_swift_symbols` sees old run_id everywhere → `stale_ratio > 50%`
threshold → prune SKIPPED via safe guard.

**Effective behavior:** prune is permanently no-op after any
no-change ingest, defeating the whole soft-delete substrate.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
  lines 197-214 (skip path)

**Reference (existing code)**

```python
if previous_body_hashes and previous_body_hashes == current_body_hashes:
    logger.info("symbol_index_swift.freshness.skip", ...)
    await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
    return ExtractorStats(outcome=SKIPPED, ...)
```

**Fix approach**

On skip path, before `finalize_ingest_run`, run a single Cypher UPDATE that
bumps `last_seen_in_run_id` + `last_seen_at` + `last_seen_in_commit` on all
:File nodes for `ctx.group_id`. This way the body_hash gate stays cheap
(skip extraction) but downstream prune sees current run_id.

Similar update propagates to :Symbol nodes via the same shadow update used
by the full-ingest path (lines 90-92).

**Acceptance**

- After SKIPPED `symbol_index_swift` run, all :File and :Symbol nodes for
  the project have `last_seen_in_run_id = current_run_id`.
- Subsequent `prune_swift_symbols` sees `stale_ratio = 0%` for unchanged
  projects (no false-positive deprecation).
- Unit test covers the skip-path bump.

**Board re-verification**

```bash
# Pre: ingest evm-kit (full); note run_id=X
# Trigger no-op skip
palace.ingest.run_extractor(name="symbol_index_swift", project="evm-kit")
# Expect: outcome=skipped, duration < 5s
# Cypher: MATCH (f:File {project_id:'project/evm-kit'}) RETURN
#         DISTINCT f.last_seen_in_run_id
# Expect: all show NEW run_id from the skip-run
```

---

## DEFECT-4 — prune_swift_symbols silently skips when upstream SKIPS

**Symptom**

In `project_analyze` pipeline, if `symbol_index_swift` returns SKIPPED
(no-op body_hash match), `prune_swift_symbols` returns:

```
"Skipped prune_swift_symbols because symbol_index_swift did not complete
successfully in this run."
```

But SKIP ≠ FAIL. The DB may still contain stale entries from earlier runs
that the new prune should clean up.

**Files**

- `services/palace-mcp/src/palace_mcp/extractors/runner.py` or
  `services/palace-mcp/src/palace_mcp/project_analyze.py` (the place that
  decides to skip prune when upstream is skipped)

**Fix approach**

Treat upstream SKIPPED as success-equivalent for the purpose of
propagating `companion_run_id`. If symbol_index_swift skipped because
body_hash matched, use the previous successful symbol_index_swift's
`ingest_run_id` (looked up from :IngestRun nodes) as the companion. This
way prune still runs and uses the correct baseline.

PE picks exact wiring. Likely combined with DEFECT-3 fix — once skip-path
bumps last_seen, companion_run_id of the skip-run itself is valid.

**Acceptance**

- After full ingest + immediate no-op re-ingest + prune, prune runs with
  correct companion_run_id and either deprecates real stale nodes or
  returns 0 deprecations cleanly (not skipped).
- Integration test covers the SKIPPED-then-prune chain.

**Board re-verification**

```python
# After fixing DEFECT-3 + DEFECT-4:
project_analyze(slug="evm-kit", extractors=["symbol_index_swift",
                                             "prune_swift_symbols"],
                force_new=True)
# Expect: both checkpoints OK (not SKIPPED for prune)
```

---

## DEFECT-5 — native deployment gap: detect_changes + get_code_snippet hardcode Docker mount paths

**Symptom**

`palace.code.detect_changes(project="evm-kit")` returns:
```
{"ok":false,"error_code":"project_not_registered",
 "message":"no mounted repo at /repos/evm-kit"}
```

`palace.code.get_code_snippet(project="evm-kit", qualified_name="...")`
finds symbol but fails to read source file, falls back to CM-sidecar (which
also can't find the project).

Both tools assume Docker mount path `/repos/<slug>`. On native MacBook
deployment, source lives in `/Users/ant013/Ios/...` (per Palace registry
`parent_mount` + `relative_path`).

**Files**

- `services/palace-mcp/src/palace_mcp/code/native_detect_changes.py`
- `services/palace-mcp/src/palace_mcp/code/native_get_code_snippet.py`
- And the snippet resolver used by get_code_snippet
  (`resolve_snippet` import location)

**Fix approach**

Use the canonical resolver to map `slug` → on-disk path:
- Read :Project node properties `parent_mount` + `relative_path`
- Combine with environment-specific mount root (Docker: `/repos`,
  native: `/Users/ant013/Ios-fresh` for `parent_mount=fresh`,
  `/Users/ant013/Ios/uw-baseline-871c0e8` for `parent_mount=baseline`,
  etc.)
- Or: store full absolute `repo_path` on :Project node at registration
  time, read it here

PE picks the approach. Recommended: add `repo_path` to :Project node on
registration (one-time migration), read it in native handlers.

**Acceptance**

- `palace.code.detect_changes(project="evm-kit")` returns actual git diff on
  the on-disk EvmKit checkout (or empty list if clean tree).
- `palace.code.get_code_snippet(project="evm-kit", qualified_name="...")`
  returns the actual snippet from the file (no FALLBACK_TO_CM).
- Works for both Docker and native deployments.

**Board re-verification**

```python
# native MacBook:
palace.code.detect_changes(project="evm-kit")
# Expect: git diff output or empty list, NOT "no mounted repo"

palace.code.get_code_snippet(project="evm-kit",
  qualified_name="EvmKit s%3A6EvmKit13RpcBlockchainC")
# Expect: actual source snippet, NOT FALLBACK_TO_CM error
```

---

## DEFECT-6 — palace-mcp running server has no auto-reload after develop merge

**Symptom**

`palace-mcp` was started 2026-05-30 (9 days before this verification).
Python process held in-memory the stale code from that time. All
verification on Layer 2 + Layer 3 initially failed because GIM-1500
namespace resolver + GIM-1519 native passthrough wiring (merged after May
30) were not loaded. After manual restart, everything worked.

This is a deployment hazard: any operator running native palace-mcp may
silently miss new merged features for weeks if they don't restart.

**Files**

- `services/palace-mcp/scripts/palace-periodic-reingest.sh` (or a new
  `palace-restart-if-stale.sh`)
- `services/palace-mcp/imac-deploy.sh` (if it should auto-restart on
  post-merge deploy)
- Documentation in `docs/contributing/branch-flow.md` or runbook

**Fix approach**

Either:
- Add post-merge hook to `release-cut-v2` workflow that triggers palace-mcp
  restart (Docker: `docker compose restart palace-mcp`; native: SIGUSR1 +
  uvicorn `--reload`)
- Or: add a `palace_health_status` field `code_loaded_at` so operators can
  see if their server is running stale code (compare `code_loaded_at` to
  latest develop commit timestamp)
- Or: auto-detect via filemod scan of `palace_mcp/__init__.py` mtime on
  each request, log warning if stale

PE picks the approach. Recommended: add `code_loaded_at` to `health_status`
+ document operator-side restart in runbook (lowest risk).

**Acceptance**

- `palace_health_status` exposes `code_loaded_at` (timestamp when server
  process started or when palace_mcp module was loaded).
- Runbook documents the post-merge restart procedure.
- Optional: warning logged when running code is >7 days stale.

**Board re-verification**

```bash
curl -s http://localhost:8765/api/health/status | jq .code_loaded_at
# Expect: ISO-8601 timestamp of process start
```

---

## Walker sequencing

CXCTO MUST open children one-by-one in this order:
1. DEFECT-1 (script scheme adapter)
2. DEFECT-2 (Config.xcconfig fallback)
3. DEFECT-3 (skip path last_seen update)
4. DEFECT-4 (prune-on-skip wiring)
5. DEFECT-5 (native file resolver)
6. DEFECT-6 (server restart hook)

After each child merges, Board reruns its specific re-verification check
(see per-defect "Board re-verification" sections above) before the next
child opens.

CX-team-1-task rule (memory `feedback-one-cx-agent-one-task`): only one
child active at a time across the entire CX team. CTO closes one child
completely (merged + Board re-verified) before opening the next.
