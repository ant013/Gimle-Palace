# Hotspot 0-Scan Investigation — 2026-05-13

**Branch:** feature/GIM-283-1-audit-status-taxonomy  
**Scope:** Task 2.5 of GIM-283-1 — B6 hotspot audit returns 0 findings  
**Investigation method:** Static code analysis (iMac access unavailable for live log inspection)

---

## Symptom

`palace.audit.run_audit(project="tron-kit")` (and other Swift Kit projects) returns 0 hotspot
findings. The `hotspot` extractor completes with `success=True` and writes ≥1 `:File` /
`:Function` nodes, but `find_hotspots(project="tron-kit")` returns an empty list.

---

## Root Cause — (C) Prerequisite Ordering

**Primary cause: `git_history` must run before `hotspot`, but `hotspot` does not enforce this.**

When `hotspot` runs without prior `git_history` data:

1. `file_walker._walk(ctx.repo_path)` returns a non-empty list of source files.
2. Lizard parses them; `parsed_files` is non-empty with correct CCN values.
3. `churn_query.fetch_churn(driver, ...)` is called. The Cypher query is:
   ```cypher
   UNWIND $paths AS path
   MATCH (f:File {project_id: $project_id, path: path})
   OPTIONAL MATCH (c:Commit)-[:TOUCHED]->(f)
   WHERE c.committed_at >= datetime($cutoff)
   RETURN path, count(c) AS churn
   ```
   — `OPTIONAL MATCH (c:Commit)` returns 0 rows because no `:Commit` nodes exist.
   — All paths get `churn = 0`.
4. `hotspot_score = math.log(ccn_total + 1) * math.log(0 + 1) = 0` for **every file**.
5. `write_hotspot_score` persists `hotspot_score = 0` for all files.
6. The audit query filters `WHERE coalesce(f.hotspot_score, 0.0) > 0` — returns **0 rows**.

The extractor reports `success=True` (0 is a valid score when churn=0). The audit pipeline
sees "hotspot ran successfully" and `FETCH_FAILED` is not triggered. But the rendered
report has no hotspot findings — silently empty, not an error.

---

## Secondary Contributing Factor — First-Run MATCH Fails

`churn_query.CHURN_CYPHER` does `MATCH (f:File {project_id: ..., path: path})`. On the very
first hotspot run, no `:File` nodes exist yet (they are written in the same `extractor.run()`
call, **after** `fetch_churn`). So `churn_map` is empty regardless of git_history state.

On the **second** hotspot run the `:File` nodes exist and the MATCH succeeds — but if
`git_history` still hasn't run, churn remains 0.

This means:
- First run: churn_map always empty (File nodes not yet written) → all scores = 0
- Subsequent runs without git_history: File nodes exist but no Commit edges → churn = 0

**Both runs produce `hotspot_score = 0` when git_history is missing.**

---

## Why the Extractor Doesn't Fail

- `ExtractorStats(nodes_written=N, edges_written=M)` with N > 0 → runner marks `success=True`
- No invariant check: "scanned_files > 0 but all scores == 0" is not detected
- The audit query's `hotspot_score > 0` filter silently eliminates all rows
- `discover_extractor_statuses` sees `success=True` → `ExtractorStatus = OK`
- The audit report shows 0 hotspot sections with no indication anything is wrong

---

## Stop-List Analysis (Root Cause B Ruled Out)

`file_walker._STOP_DIRS` = `{".git", ".venv", ".gradle", "build", "dist", ...}`
`file_walker._FIXTURE_STOP_PARTS` = `("tests", "extractors", "fixtures")`

For Swift Kit repos (e.g. `tron-kit`):
- Source files live under `Sources/<Module>/...` — not matched by any stop pattern
- `build` stop dir does not affect iMac checkout paths (build artifacts in DerivedData)
- The `_has_subseq` check is a consecutive-subsequence matcher — `Sources/tests/extractors/fixtures` would match but is not a realistic path in a Swift Kit

**Stop-list overzealous exclusion is ruled out as the primary cause.**

---

## Mount-Path Analysis (Root Cause A Ruled Out)

`_resolve_repo_path` returns `None` if `(candidate / ".git").exists()` is False, which
triggers a `_PrecheckFail` — the extractor never runs at all. Since the symptom is
"`success=True` with 0 findings" (not a failed run), mount-path mismatch that prevents
execution is ruled out.

A partial-mount-path issue (repo mounted but wrong directory, so `file_walker._walk` returns 0
files) could explain `scanned_files = 0`. This is addressed by Task 2.7's invariant
`data_mismatch_zero_scan_with_files_present` (detects 0 scanned_files when Neo4j already
has `:File` nodes from a prior run).

---

## Fix Plan

### Task 2.6 — Prerequisite guard in `hotspot/extractor.py`

Add an explicit check at the start of `hotspot.run()`:
- Query: does a successful `:IngestRun` for `git_history` exist for this project?
- If not → raise `_HotspotError("prerequisite_missing", "run git_history before hotspot")`

This converts a silent 0-scan into an explicit `RUN_FAILED` with `status_reason = "prerequisite_missing"`.

### Task 2.7 — Three loud-fail invariants

After lizard runs:

| Condition | Error code | Meaning |
|-----------|-----------|---------|
| `scanned_files == 0 AND db_file_count > 0` | `data_mismatch_zero_scan_with_files_present` | Mount/stop-list mismatch |
| `scanned_files == 0 AND db_file_count == 0` | `empty_project` | No code files found |
| `scanned_files > 0 AND parsed_functions == 0` | `lizard_parser_zero_functions` | Lizard parser broken |

---

## Recommended Ordering Fix (Shell Script)

In `paperclips/scripts/ingest_swift_kit.sh`, `git_history` should always precede `hotspot`:

```bash
# Correct order
palace.ingest.run_extractor(name="git_history", project="$SLUG")
palace.ingest.run_extractor(name="hotspot", project="$SLUG")
```

The prerequisite guard in Task 2.6 makes this ordering requirement explicit and machine-enforceable.
