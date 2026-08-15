# Spec: Disambiguate zero-result code queries (P0 freshness + P1 unresolved≠0)

**Status:** draft for voltAgent review → implement. **Date:** 2026-06-28.
**Scope:** `find_references`, `semantic_search` (+ trivial `last_ingest`). **Deferred:** P2 semantic floor (separate ranking slice — needs ANN perf benchmark), P3 identity-doc.

## Problem

A `0`/`symbol_not_found` result from a code tool is **ambiguous** — the caller cannot tell:
1. **Index lag** — the symbol exists in the working tree but the index reflects an older committed state (SCIP injected at the indexed commit; uncommitted/working-tree edits are invisible). Operator repro: a just-created `AaTransactionRecord` → `symbol_not_found`, `PendingUserOperationRecordStorage.clear` → `total_found:0`, while `grep` finds both — until committed.
2. **Name didn't resolve** — `find_references("PimlicoProvider.PaymasterMode")` → `total_found:0` (silent), because real symbols are SCIP-encoded (`s%3A8Stable_D15PimlicoProviderC…`) and the human dotted name never matched. Indistinguishable from "0 genuine references".
3. **Genuinely zero** — the symbol resolved and truly has no references.

Today (verified live 2026-06-28): `find_references` returns `indexed_commit/commits_behind_head/stale/dirty_working_tree` keys but **all `null`**; `semantic_search` lacks them or returns `null`. The freshness machinery already exists for `get_code_snippet`, `semantic_search`(partly) and `get_project_overview` via `inspect_freshness()` — it is simply **not wired into `find_references`**, and `dirty_working_tree` is not computed anywhere.

## Goals

- Every `find_references` and `semantic_search` response carries a populated freshness block: `indexed_commit`, `commits_behind_head`, `stale`, `dirty_working_tree`.
- `find_references` distinguishes **unresolved/ambiguous name** from **genuine zero**, with `did_you_mean`.
- Net contract: `0 refs + stale:false + dirty_working_tree:false + resolved` = "really none"; otherwise the caller knows *why* it's zero.

Non-goal (this slice): incremental reindex / file-watch (rev2 non-goal); per-project ANN floor (P2); merging the 4 identity schemes (P3).

## Design

### P0 — freshness stamping

Existing substrate (`code/snippet_provider.py`):
- `FreshnessResult{indexed_commit, commits_behind_head, stale}` (frozen dataclass).
- `inspect_freshness(repo_root, commit_sha)` → runs `git rev-parse HEAD` (5s timeout), compares to the indexed commit.

Changes:
1. **Add `dirty_working_tree: bool = False`** to `FreshnessResult`. In `inspect_freshness`, when `repo_root` is a git repo, set it from `git status --porcelain` (non-empty ⇒ dirty). This is the field that catches the operator's exact symptom (uncommitted edits).
2. **One shared resolver** `resolve_project_freshness(driver, project) -> FreshnessResult`:
   - resolve `repo_path` for the slug (reuse `resolve_project`/registry `repo_path`),
   - resolve the indexed commit (reuse `project_analyze._read_project_indexed_commit`),
   - call `inspect_freshness(repo_path, indexed_commit)`.
   Consumed by `find_references` and `semantic_search` (and `get_project_overview` keeps its existing call).
3. **Wire it into `find_references`** (`code_composite.py`): stamp the four fields onto the response (currently null placeholders).
4. **Ensure `semantic_search`** (`find_semantic.py:_load_freshness`) actually resolves the indexed commit so its fields are non-null (today null when `commit_sha` is unresolved).
5. **`stale` semantics:** `stale = commits_behind_head > 0`. `dirty_working_tree` is reported **separately** (do NOT fold dirty into `stale` — a dirty tree at the indexed HEAD is not "index behind committed HEAD"; conflating them loses signal). Document both.

### P1 — unresolved ≠ zero in `find_references`

In `code_composite.py` resolution:
- If the qualified_name resolves to **≥1 symbol** and that symbol has 0 reference occurrences → genuine zero: `ok:true, total_found:0, resolution:"resolved"`.
- If it resolves to **no symbol** → `ok:true, error_code:"symbol_not_found", resolution:"unresolved", did_you_mean:[…]`.
- If it is **ambiguous** (short/dotted name folds to >1 distinct symbol) → `ok:true, error_code:"ambiguous_qualified_name", resolution:"ambiguous", candidates:[…]` (project-scoped; do NOT silently pick one).
- `did_you_mean`/`candidates`: cheap fuzzy match of the requested name's last path-component against project symbols' demangled short-names (top-N by edit-distance/prefix). Bounded N (≤5).

### P4 — trivial

Populate `last_ingest_finished_at` in `get_project_overview`/`list_projects` from the same source `get_project_overview` already reads ingest state from (no new query if the IngestRun timestamp is already loaded).

## Open questions (resolve in review)

- **Q1 Freshness cost per call.** `git rev-parse HEAD` + `git status --porcelain` on every code response, on 258k-symbol repos. Cache `FreshnessResult` per `(project, indexed_commit)` with a short TTL? Or accept the ~few-ms git cost? `git status` is the heavier of the two.
- **Q2 `dirty_working_tree` scope.** Whole-repo `git status --porcelain` is O(working-tree); is a path-scoped check meaningful, or is repo-level dirty the right signal?
- **Q3 `did_you_mean` source.** Demangled SCIP short-names require W0 canonical names (may be absent). Fall back to substring match on raw qn? Acceptable for v1?
- **Q4 error_code taxonomy.** New `resolution` enum + reuse `symbol_not_found`/`ambiguous_qualified_name` — avoid the "tautological isError" trap (don't assert only `ok==false`).
- **Q5 `stale` vs `dirty` contract.** Confirm separate fields (not folded) is the desired wire contract.

## Acceptance

- `find_references(resolved symbol with no refs)` → `total_found:0, resolution:"resolved", stale:false, dirty_working_tree:false`.
- `find_references(unresolved name)` → `error_code:"symbol_not_found", resolution:"unresolved", did_you_mean` non-empty when near matches exist.
- `find_references(ambiguous short name)` → `error_code:"ambiguous_qualified_name", candidates` listed.
- `semantic_search` + `find_references` both carry non-null `indexed_commit`+`commits_behind_head`; `stale:true` when `commits_behind_head>0`; `dirty_working_tree:true` after an uncommitted edit in the repo.
- **Negative/unit:** non-git repo → freshness fields null, no crash; dirty tree detection via a seeded fixture; an unresolved name with NO near matches → `did_you_mean:[]` (not null-vs-empty confusion); freshness git timeout → degrade to null, not error.

## Review resolutions (voltAgent: architect / performance / code, 2026-06-28)

- **Correction:** `find_references` emits **no** freshness keys today (not null placeholders) → add to **all** envelopes incl. the unresolved/error path (else the operator's new-uncommitted-symbol repro stays signal-less).
- **P1 gate (HIGH):** `code_composite.py:1429` `_needs_human_resolution` gate skips resolution for dotted names (`.`, no `%3`/`scip-`) with no CM session → literal → Tantivy → silent zero. Fix: always attempt resolution + capture an explicit `resolution` ∈ {resolved, unresolved, ambiguous}.
- **Q1:** two caches — `rev[(repo, indexed_commit)]` TTL 60s; `dirty[repo]` invalidated by `os.stat('.git/index').st_mtime_ns`. Resolve **once per unique project** (dedup), not per hit (semantic calls it per-hit today, `find_semantic.py:1138`).
- **Q2:** `git status --porcelain --untracked-files=no` (~20ms; untracked files can't be SCIP-indexed). Never `-uall` (~780ms). Inside the existing `timeout=5` try/except → degrade to null, never raise.
- **Q3:** reuse `canonical_symbol_short_name` demangler (`symbol_identity.py:139`, no W0 needed) ranked by edit-distance on the requested last component, top-5; skip empty/non-identifier demangles (method/property garble guard); prefer stored `short_name`.
- **Q4:** unresolved/ambiguous keep the existing **`ok:false` + `error_code`** (`symbol_not_found`/`ambiguous_qualified_name`) envelope, extended with `did_you_mean`/`candidates` + freshness; genuine-zero = **`ok:true` + `total_found:0` + `resolution:"resolved"`** + freshness. Distinction is the `ok` flag (non-tautological: genuine-zero is `ok:true`). Do not fork a parallel `ok:true`+`error_code` shape.
- **Q5:** keep `stale` (commits-behind) and `dirty_working_tree` as separate booleans; optional derived `freshness_status` later.
- **P4 re-scope:** `get_project_overview` already populates `last_ingest_finished_at` + freshness; only `list_projects` needs it.
- **Home/seam:** move `FreshnessResult`+`inspect_freshness`+`resolve_project_freshness` to `code/freshness.py` (cross-cutting; snippet_provider must not gain a neo4j dep). Decorator-at-`code_router` boundary is the clean long-term application point; v1 wires `find_references` + dedup'd `semantic` directly.

## Test plan

- Unit: `inspect_freshness` dirty-tree branch (mock/temp git repo); `FreshnessResult.dirty_working_tree` default; resolution-classifier (resolved / unresolved / ambiguous) on fixture symbols.
- Integration (live re-probe pasted in PR): the three operator repros after fix.
