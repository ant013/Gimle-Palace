---
title: Code ownership extractor — file-level blame_share + recency-weighted churn
slug: code-ownership-extractor
date: 2026-05-06
status: proposed
paperclip_issue: GIM-NN
predecessor_sha: 0a9c2363a
authoring: Board+Claude
team: Claude
roadmap_item: "#32 Code Ownership Extractor"
roadmap_source: "docs/roadmap.md §2.3 Historical, row #32 (verified 2026-05-06 by Board+Claude after GIM-195 hotspot merged)"
---

# Code ownership extractor (Roadmap #32)

## 1. Context

Roadmap §2.3 row #32 — Code Ownership Extractor. Second Claude-team
Phase 2 historical slice. The first (#44 Hotspot, GIM-195) closed on
develop@`14b0257`; #22 Git History (GIM-186, `b0dd44d`) is the foundation
all historical extractors consume.

**Product question this slice answers**: «Who owns this file?» — for
each `:File` in a project, identify the top-N humans who currently know
the code, with weights that combine *truth-of-record* (who wrote the
lines that exist now) and *active maintenance* (who has been touching
it lately).

**Source-of-truth artefacts already on develop@`0a9c2363a`:**

- `:Author {provider, identity_key, email, name, is_bot, ...}` —
  `extractors/git_history/neo4j_writer.py:_MERGE_AUTHOR_CYPHER`
- `:Commit {sha, committed_at, parents, ...}` — same writer; computed
  property `is_merge` derives from `len(parents) > 1`
- `(:Commit)-[:AUTHORED_BY]->(:Author)` — same writer
- `(:Commit)-[:TOUCHED]->(:File)` — `_MERGE_TOUCHED_CYPHER`; binary
  signal only (no LOC delta — see R1)
- `:File {project_id, path}` — same writer
- Foundation: `BaseExtractor`, `ExtractorRunContext`, `ExtractorStats`,
  `ensure_custom_schema`, Pydantic v2 frozen models pattern,
  `PALACE_RECENCY_DECAY_DAYS=30` constant

**Operator-facing query this slice ships:**

`palace.code.find_owners(file_path, project, top_n=5)` → ranked owners
`(author_email, author_name, weight, blame_share, recency_churn_share,
last_touched_at)` with provenance metadata `(last_run_at, total_authors)`.

## 2. Scope

### IN (v1)

- New extractor `code_ownership` registered in `EXTRACTORS` registry
  (`extractors/registry.py`).
- New MCP tool `palace.code.find_owners` registered next to existing
  `palace.code.find_references` / `palace.code.find_hotspots` (path:
  `services/palace-mcp/src/palace_mcp/code/find_owners.py`).
- Per-file `pygit2.blame` walk on current HEAD of mounted repo
  (`/repos/<slug>`).
- Recency-weighted churn aggregation via Cypher over existing
  `:Commit/:TOUCHED` edges (no fresh git walk for churn).
- `.mailmap` support — implemented as `MailmapResolver` in
  `extractors/code_ownership/mailmap.py`. v1 prefers
  `pygit2.Mailmap.from_repository(repo)` if the bound libgit2 build
  exposes it; otherwise falls back to a small in-process parser
  following the format documented in `git help check-mailmap`
  (entries: `Real Name <real@x> Old Name <old@x>` and three other
  forms). Either path yields `canonicalize(name, email) → (name,
  email)`. If `.mailmap` is absent → identity passthrough. The
  resolver is unit-tested independently of the pygit2 path.
- Linear-combo scoring `weight = α × blame_share + (1-α) × recency_churn_share`,
  α default `0.5`, env-tunable `PALACE_OWNERSHIP_BLAME_WEIGHT`.
- Per-file incremental refresh — `:OwnershipCheckpoint{project_id,
  last_head_sha, last_completed_at}`. Re-run blames only files in DIRTY
  set (changed since checkpoint or new in HEAD); deletes edges of
  files removed in HEAD; preserves edges of unchanged files.
- Atomic-replace transaction on the per-file edge set: external readers
  see only consistent snapshots.
- Bot exclusion (`a.is_bot=true`) and merge-commit exclusion
  (`c.is_merge=true`) at both blame and churn sides.
- Update `CLAUDE.md ## Extractors` with operator workflow.

### OUT (v1, explicitly deferred)

- F1. **Symbol-level ownership** — `(:Symbol)-[:OWNED_BY]->(:Author)`
  via blame ∩ symbol_index DEF line spans. Big surface change, multi-
  language complications. Followup slice when first agent demands it.
- F2. **Module/directory persisted aggregates** — `(:Directory)-[:OWNED_BY]->()`.
  Cypher aggregation on demand is cheap (Q6 rationale); no need to
  persist.
- F3. **Bundle-aware run** — `run_extractor(name="code_ownership",
  bundle="uw-ios")` iterating 41 HS Kits. Followup slice; v1 operator
  scripts the loop manually.
- F4. **Cross-member `:CodeOwner` aggregation** — bridge node merging
  ownership across bundle members. Stacked on F3.
- F5. **Heuristic identity merge** — auto-link split git/github
  identities without `.mailmap`. v1 falls back gracefully on missing
  `.mailmap`; if UW data shows widespread split-identity pain,
  followup slice introduces `:CodeOwner` heuristic merge.
- F6. **Orphan-file detection** — `find_orphan_files` query (bus-factor
  ≤ 1 + author inactive ≥ N days). Stretch product surface; needs
  configurable "active" threshold and additional tests.
- F7. **Module-aggregate query** — `find_module_owners(project,
  prefix)` MCP tool. Cypher on `:OWNED_BY` is enough for v1; tool
  wrapper is a 50-LOC followup if demand surfaces.
- F8. **LOC-weighted churn** — extending `:TOUCHED` with
  `lines_added/deleted` requires GIM-186 schema migration. v1 uses
  count-based churn with recency decay. Followup if signal proves
  insufficient.
- F9. **`code-maat` / `hercules` integration** — Tornhill's truck-
  factor + temporal coupling. Subprocess complications, JAR/Go
  binary dependency. Roadmap mentions both; v1 ships with pure
  pygit2 + Cypher and proves value; subprocess tools follow if signal
  needs them.
- F10. **Cross-language blame** — git treats all text identically;
  no language-aware split. Same as F1 — symbol-level slice.

## 3. Decisions and trade-offs (rationale captured during brainstorm)

- **R1 (signal source) — Hybrid: blame on HEAD + count-based churn from graph.**
  GIM-186's `:TOUCHED` edge has no LOC delta, so a re-walk would be
  required for LOC-weighted churn (extends GIM-186 schema, doubles
  walks). Pure-graph count-based churn loses LOC granularity but is
  free; HEAD blame is the single most valuable ownership signal and
  costs one tree walk. v1 takes the cheap-but-true combo.

- **R2 (granularity) — File-level only.** Symmetric with #44 Hotspot
  (GIM-195). Symbol-level (F1) requires bridging to `symbol_index`
  outputs which differ per language (Solidity v1 has no USE
  occurrences; Swift uses custom emitter spans). Directory aggregates
  (F2) are cheap Cypher on demand.

- **R3 (identity) — `.mailmap`-aware, no heuristic merge.** UW history
  spans 2017-2026; multiple email-per-person is real. `.mailmap` is
  the standard git solution. v1 implements its own `MailmapResolver`
  (small parser, format documented at `git help check-mailmap`);
  pygit2's `Mailmap` is preferred if exposed by the bound libgit2,
  else custom parser is used unconditionally. Heuristic merge (F5)
  risks false-positive cross-author merges and is deferred. **Edge
  case — synthetic canonical email**: if `.mailmap` rewrites to an
  email never used in any commit (rare), the resolver returns the
  canonical pair and the writer MERGEs a virtual `:Author{provider:
  'git', identity_key: canonical_email_lc}` node. Documented in §4
  Phase 4.

- **R4 (MCP surface) — single tool: `find_owners`.** Symmetric with
  #44's `find_hotspots`. Orphan-files / module-owners are followups
  (F6/F7) with their own tuning knobs.

- **R5 (scoring) — `α × blame + (1-α) × churn`, α=0.5 default.** Two
  sub-questions ("who wrote it" vs "who maintains it") both matter;
  α=0.5 is a neutral middle. Env-tunable
  `PALACE_OWNERSHIP_BLAME_WEIGHT` for operator override. Each edge
  records `alpha_used` for reproducibility across env changes.

- **R6 (scope) — single-project per run.** Symmetric with #44 and
  #5 (dependency_surface). Bundle support (F3) is structurally
  identical to GIM-182 multi-repo SPM ingest; can be lifted later.

- **R7 (incrementality) — per-file incremental with checkpoint.** UW
  Android (~3k Kotlin/Java files) full blame walk is 5-15 min; on
  per-merge refresh that's prohibitive. Checkpoint + DIRTY-set diff
  brings re-run cost to seconds for typical refreshes.

- **R8 (bots/merges) — exclude.** GIM-186 already detects bots
  (`Author.is_bot=true`); merges are conflict resolution, not
  authorship.

## 4. Architecture

### File layout

```
services/palace-mcp/src/palace_mcp/extractors/code_ownership/
├── __init__.py              # CodeOwnershipExtractor export
├── extractor.py             # orchestrator: BaseExtractor.extract impl
├── checkpoint.py            # :OwnershipCheckpoint read/write/init
├── mailmap.py               # .mailmap parser + MailmapResolver
├── blame_walker.py          # pygit2.blame per file → BlameAttribution
├── churn_aggregator.py      # Cypher: :TOUCHED → recency-weighted shares
├── scorer.py                # weight() formula + per-file normalization
├── neo4j_writer.py          # atomic-replace tx for :OWNED_BY edges
├── schema_extension.py      # extends ensure_custom_schema()
└── models.py                # OwnershipEdge, OwnershipCheckpoint,
                             #   OwnershipRunSummary, BlameAttribution,
                             #   ChurnShare (Pydantic v2 frozen)

services/palace-mcp/src/palace_mcp/code/
└── find_owners.py           # MCP tool wrapper (Cypher → typed envelope)
```

### Phase pipeline

```
Phase 0 — bootstrap
  • check_resume_budget(prev_error_code)        ← substrate
  • ensure_custom_schema(driver) extended       ← schema_extension.py
  • load_or_init_checkpoint(project_id)
  • repo = pygit2.Repository("/repos/<slug>")
  • mailmap = MailmapResolver.from_repo(repo)   ← may be no-op
  • bot_identity_keys = {row.identity_key
        for row in MATCH (a:Author {provider: 'git'})
                   WHERE a.is_bot = true
                   RETURN a.identity_key}
    // small set (typically 1–5 bots per project); used client-side
    // by blame_walker to drop bot lines and by writer to skip bot edges.
  • assert there is at least one :Commit{project_id} in graph else
    fail with git_history_not_indexed

Phase 1 — DIRTY/DELETED set computation
  • current_head = repo.head.target.hex
  • if checkpoint.last_head_sha is None:
      DIRTY = all files in repo.head.peel().tree (recursive)
      DELETED = ∅
  • else if last_head_sha == current_head:
      → emit success no-op (no edges touched, checkpoint + run written)
  • else:
      diff = pygit2.Diff between last_head_sha and current_head
      DIRTY = files modified or added in diff
      DELETED = files removed in diff
  • assert len(DIRTY) ≤ PALACE_OWNERSHIP_MAX_FILES_PER_RUN

Phase 2 — blame walk (DIRTY only)
  • for path in DIRTY:
      try blame = repo.blame(path, newest_commit=current_head)
      except (pygit2 binary/symlink/submodule) → log warn, skip path
      lines_per_raw = aggregate hunks per (raw_email, raw_name)
      for (raw_name, raw_email), lines in lines_per_raw:
          (canonical_name, canonical_email) =
              mailmap.canonicalize(raw_name, raw_email)
          canonical_id = canonical_email.lower()
          if canonical_id in bot_identity_keys: continue
          accumulate lines under canonical_id
  • result: dict[path, dict[canonical_id, BlameAttribution(
              lines, canonical_name, canonical_email)]]

Phase 3 — churn aggregation (DIRTY only)
  • for path in DIRTY:
      MATCH (c:Commit {project_id: $proj})-[:TOUCHED]->(f:File {path: $path})
      MATCH (c)-[:AUTHORED_BY]->(a:Author)
      WHERE NOT a.is_bot AND NOT c.is_merge
      WITH a.identity_key AS raw_id,
           a.name AS raw_name,
           c.committed_at AS ts
      RETURN raw_id, raw_name, ts
      // raw rows; aggregation happens in Python after mailmap canonicalize
  • client-side: for each row,
      (canonical_name, canonical_email) = mailmap.canonicalize(raw_name, raw_id)
      canonical_id = canonical_email.lower()
      if canonical_id in bot_identity_keys: continue
  • client-side aggregate per (path, canonical_id):
      recency_score = Σ exp(-Δseconds / (decay_days × 86400))
      last_touched_at = max(ts)
      commit_count = len(rows)
  • result: dict[path, dict[canonical_id, ChurnShare(
              recency_score, last_touched_at, commit_count,
              canonical_name, canonical_email)]]

Phase 4 — scoring + atomic replace write
  • merge blame and churn dicts per file (keyed by canonical_id)
  • normalize per file, AFTER bot exclusion:
      blame_share[a]         = lines[a] / Σ lines[non-bot authors]
      recency_churn_share[a] = recency[a] / Σ recency[non-bot authors]
  • Note: normalization denominators exclude bot lines/commits, so
    Σ blame_share = Σ recency_churn_share = 1.0 (within ε) over the
    non-bot authors that appear on the file. Files with only bot
    contributors → no edges emitted (zero owners).
  • weight = α × blame_share + (1-α) × recency_churn_share
  • if a file has only churn evidence but no blame (file changed but
    blame_walker skipped — e.g., binary): blame_share = 0 for all,
    weight = (1-α) × recency_churn_share. Conversely, if blame
    succeeded but churn graph is empty (file is part of HEAD tree but
    has no `:TOUCHED` history — possible if GIM-186 ran with
    incomplete history): recency_churn_share = 0 for all,
    weight = α × blame_share.
  • emit OwnershipEdge per (path, canonical_id)
  • single tx:
      UNWIND $dirty_paths_and_deleted AS p
      MATCH (f:File {project_id: $proj, path: p})
            -[r:OWNED_BY {run_id_provenance: 'extractor.code_ownership'}]
            ->()
      DELETE r
      ;
      UNWIND $edges AS e
      MATCH (f:File {project_id: $proj, path: e.path})
      // MERGE author on canonical: handles synthetic mailmap targets
      // (canonical email that never appeared as raw commit email).
      // For non-synthetic cases this is idempotent — Author already exists.
      MERGE (a:Author {provider: 'git', identity_key: e.canonical_id})
        ON CREATE SET a.email = e.canonical_email,
                      a.name = e.canonical_name,
                      a.is_bot = false,
                      a.first_seen_at = e.first_seen_at,
                      a.last_seen_at = e.last_touched_at,
                      a._synthetic_from_mailmap = true
      MERGE (f)-[r:OWNED_BY]->(a)
      SET r.weight = e.weight,
          r.blame_share = e.blame_share,
          r.recency_churn_share = e.recency_churn_share,
          r.last_touched_at = e.last_touched_at,
          r.lines_attributed = e.lines_attributed,
          r.commit_count = e.commit_count,
          r.run_id_provenance = $run_id,
          r.alpha_used = $alpha
  • update :OwnershipCheckpoint{last_head_sha=current_head,
                                 last_completed_at=NOW(),
                                 run_id=$run_id}
  • write :OwnershipRun success node

Phase 5 — stats
  • return ExtractorStats(nodes_written=run+checkpoint, edges_written, …)
```

## 5. Schema

### New nodes

**`:OwnershipCheckpoint`** (one per project)

| Property | Type | Note |
|----------|------|------|
| `project_id` | string | unique key |
| `last_head_sha` | string \| null | nullable on bootstrap |
| `last_completed_at` | datetime (UTC) | last successful run timestamp |
| `run_id` | string (UUID) | provenance |
| `updated_at` | datetime (UTC) | tombstone for stale-checkpoint detection |

`CREATE CONSTRAINT ownership_checkpoint_unique IF NOT EXISTS FOR (c:OwnershipCheckpoint) REQUIRE c.project_id IS UNIQUE;`

**`:OwnershipRun`** (one per run, append-only; mirrors substrate `:IngestRun`)

| Property | Type | Note |
|----------|------|------|
| `run_id` | string (UUID) | unique key |
| `project_id` | string | indexed |
| `source` | string | hardcoded `"extractor.code_ownership"` |
| `started_at` | datetime | UTC |
| `completed_at` | datetime \| null | null on crash |
| `success` | bool | |
| `head_sha` | string | target HEAD of run |
| `prev_head_sha` | string \| null | for diff-tracing |
| `dirty_files_count` | int | files re-blamed |
| `deleted_files_count` | int | files removed in HEAD |
| `edges_written` | int | new `:OWNED_BY` written |
| `edges_deleted` | int | old `:OWNED_BY` removed |
| `error_code` | string \| null | per `ExtractorErrorCode` |
| `error_message` | string \| null | truncated 1024 |

`CREATE CONSTRAINT ownership_run_unique IF NOT EXISTS FOR (r:OwnershipRun) REQUIRE r.run_id IS UNIQUE;`
`CREATE INDEX ownership_run_project IF NOT EXISTS FOR (r:OwnershipRun) ON (r.project_id, r.completed_at);`

### New edge

**`(:File)-[:OWNED_BY]->(:Author)`**

| Property | Type | Note |
|----------|------|------|
| `weight` | float [0..1] | combined score |
| `blame_share` | float [0..1] | line-share in HEAD blame |
| `recency_churn_share` | float [0..1] | decay-weighted commit-share |
| `last_touched_at` | datetime | max committed_at by this author on this file |
| `lines_attributed` | int | absolute blame line count |
| `commit_count` | int | absolute commit count (no decay) |
| `run_id_provenance` | string (UUID) | run that wrote the edge |
| `alpha_used` | float | α at write time |

Cardinality: one edge per `(File, Author)` per project (enforced by
`MATCH (f) MATCH (a) MERGE (f)-[r:OWNED_BY]->(a)`).

`CREATE INDEX file_owned_by_weight IF NOT EXISTS FOR ()-[r:OWNED_BY]->() ON (r.weight);`

### Read-only inputs (from GIM-186)

- `:File {project_id, path}` — uniqueness on `(project_id, path)`
- `:Author {provider, identity_key, ..., is_bot}` — uniqueness on
  `(provider, identity_key)`
- `:Commit {sha, committed_at, parents}` — uniqueness on `sha`
- `(:Commit)-[:TOUCHED]->(:File)` — provided
- `(:Commit)-[:AUTHORED_BY]->(:Author)` — provided

### Schema bootstrap

`extractors/code_ownership/schema_extension.py` exports
`ensure_ownership_schema(driver)` which is invoked from the extractor's
Phase 0. Idempotent — uses `IF NOT EXISTS` on every constraint/index.
Drift detection follows substrate convention.

## 6. Configuration (env vars)

Added to `PalaceSettings` (`config.py`), prefix `PALACE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PALACE_OWNERSHIP_BLAME_WEIGHT` | `0.5` | α in `weight = α × blame + (1-α) × churn`; range `[0.0, 1.0]` enforced; out of range → `extractor_config_error` |
| `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` | `50000` | hard cap on DIRTY set size; exceeded → `ownership_max_files_exceeded` |

Reused from substrate (no change):
- `PALACE_RECENCY_DECAY_DAYS = 30` — half-life for `exp(-Δdays/T)`

## 7. MCP tool contract

### `palace.code.find_owners`

**Args:**
| Name | Type | Default | Constraint |
|------|------|---------|------------|
| `file_path` | str | (required) | non-empty |
| `project` | str | (required) | must match `slug_pattern` |
| `top_n` | int | `5` | `1 ≤ top_n ≤ 100` |

**Success envelope:**
```python
{
    "ok": True,
    "file_path": "services/palace-mcp/src/palace_mcp/code/find_owners.py",
    "project": "gimle",
    "owners": [
        {
            "author_email": "anton@example.com",
            "author_name": "Anton Stavnichiy",
            "weight": 0.42,
            "blame_share": 0.55,
            "recency_churn_share": 0.29,
            "last_touched_at": "2026-04-12T18:42:01Z",
            "lines_attributed": 145,
            "commit_count": 12,
        },
        # ...
    ],
    "total_authors": 14,    # before top_n filter
    "last_run_at": "2026-05-06T08:30:11Z",
    "head_sha": "0a9c2363a39b94f14e5bcdc5e3db44233c8a349c",
    "alpha_used": 0.5,
}
```

**Error envelopes:**

| `error_code` | Trigger |
|--------------|---------|
| `unknown_file` | `:File {project_id, path}` does not exist |
| `project_not_registered` | no `:Project {slug}` |
| `ownership_not_indexed_yet` | no `:OwnershipCheckpoint` for project |
| `slug_invalid` | project slug fails validation |
| `top_n_out_of_range` | `top_n` outside `[1, 100]` |

**Resolution order** (first match wins):

1. validate `slug` and `top_n` — fail with `slug_invalid` /
   `top_n_out_of_range` before hitting Neo4j.
2. check `(:Project {slug})` exists — fail `project_not_registered`.
3. check `(:OwnershipCheckpoint {project_id: $slug})` exists — fail
   `ownership_not_indexed_yet`.
4. check `(:File {project_id: $slug, path: $file_path})` exists —
   fail `unknown_file` if not.
5. **Success-empty when the file exists but has no `:OWNED_BY`** —
   binary/skipped/all-bot files. Return `ok=True` with `owners=[]`,
   `total_authors=0`. NOT an error — the file is known but has no
   human ownership signal.

## 8. Error handling and idempotency

### `ExtractorErrorCode` additions (in `foundation/errors.py`)

| Code | When |
|------|------|
| `ownership_max_files_exceeded` | DIRTY > `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` |
| `git_history_not_indexed` | `count((c:Commit{project_id:$slug}))` = 0 |
| `mailmap_parse_error` | `.mailmap` present but unparseable; logged, run continues without mailmap |
| `blame_failed` | per-file warning only — NOT a run-failure code; aggregated in `run.error_message` summary if non-zero |
| `head_unchanged_no_dirty` | informational success-shortcut, not a real error code |

Existing substrate codes used as-is: `repo_not_mounted`,
`project_not_registered`, `extractor_config_error`,
`extractor_runtime_error`.

### Idempotency invariants

1. **No-op re-run** — same HEAD, no DIRTY → 0 edges touched; new
   `:OwnershipRun` written for audit; checkpoint `last_completed_at`
   advances.
2. **Identical re-run** — same DIRTY set → `MERGE … SET …` rewrites
   identical property values; net change zero.
3. **Crash recovery** — checkpoint updates ONLY in Phase 4 final tx.
   Crash in Phase 1/2/3 → checkpoint stale → next run recomputes
   DIRTY identically → atomic-replace wipes any partial edges from
   the failed attempt.
4. **`alpha_used` provenance** — operator can audit which edges were
   computed at which α. Mixed-α state is possible if env was changed
   mid-stream; on next full re-walk per file, `alpha_used` updates.
5. **Atomic per-tx scope** — DELETE + MERGE for all DIRTY paths in a
   single Cypher session.run() bound by an outer
   `async with driver.session(...) as session: async with session.begin_transaction()`.

### Edge cases (per Q7 confirmation)

| Case | Behavior |
|------|----------|
| File renamed via `git mv` | pygit2 blame uses new path; churn from `:TOUCHED` uses new path. History before rename is lost (documented limitation, runbook §"Known issues"). |
| Submodule (gitlink) | `pygit2.blame` raises → log warn, skip path. `:File` may exist (GIM-186 indexes path) but no `:OWNED_BY`. |
| Symlink / binary / fixture-stop-listed | Same handling as submodule — skip with warn. |
| File deleted in HEAD | In DELETED-set; old edges removed in Phase 4 atomic tx. No new edges written (no blame target). |
| File only in HEAD (uncommitted) | Not in `:File` graph → not in DIRTY → ignored. Picked up after first commit. |
| Two authors with identical mailmap canonical | Edges merge: `lines_attributed` sums, `commit_count` sums, `recency_score` sums; one final `:OWNED_BY` per canonical author per file. |
| `.mailmap` missing | `MailmapResolver.canonicalize()` is identity. No-op. |
| `.mailmap` unparseable | `mailmap_parse_error` warning; run continues with identity passthrough. |

## 9. Acceptance criteria

A successful run produces, given a project `gimle` mounted at
`/repos/gimle` with GIM-186 indexed:

1. **Bootstrap completes without checkpoint.** First-ever run with
   `last_head_sha = NULL` blames every file in HEAD tree; produces
   `:OwnershipCheckpoint` and `:OwnershipRun{success=true}`; emits
   `:OWNED_BY` edges for every non-binary, non-submodule file.

2. **No-op re-run when HEAD unchanged.** Second run with identical
   HEAD writes 0 new edges, deletes 0 edges, but persists a new
   `:OwnershipRun` and advances `last_completed_at`.

3. **Incremental refresh after a single-file edit.** After modifying
   one file and committing, re-run blames exactly one file; existing
   edges for the other files remain untouched (verified by sampling
   `r.run_id_provenance` — unchanged for non-DIRTY).

4. **Deletion handling.** `git rm` a file, commit, re-run. Old
   `:OWNED_BY` edges for the deleted file are removed; no new edges
   target the missing path.

5. **`.mailmap` deduplication.** Fixture has author committing with
   two emails (`old@x.com`, `new@y.com`). With `.mailmap` mapping
   both to canonical `new@y.com`, the resulting edge has
   `lines_attributed` = sum across both. Without `.mailmap`, two
   separate `:OWNED_BY` edges exist.

6. **Bot exclusion.** Fixture commit by author with `is_bot=true`
   does not produce `:OWNED_BY` edges. Bot lines and bot commits are
   excluded from per-file normalization denominators — humans on a
   file with bot contributions still see `Σ blame_share = 1.0` and
   `Σ recency_churn_share = 1.0` over their non-bot cohort. Bot
   commits remain in `:Commit` (read-only from GIM-186).

7. **Merge-commit exclusion.** Merge commit's author is the merger;
   churn aggregator filters `c.is_merge=true` so the merger does not
   accumulate spurious recency_churn_share for files from the merged
   branch. **Documented trade-off**: legitimate conflict-resolution
   work in a merge commit is also not credited in v1. Acceptable for
   typical UW workflow (merges are mostly fast-forward or CI-merge
   bot); revisit if real merger contributions become significant.

8. **Per-file weight normalization.** For every file with
   `:OWNED_BY` edges, `Σ blame_share = 1.0 ± ε`,
   `Σ recency_churn_share = 1.0 ± ε`, `Σ weight = 1.0 ± ε`
   (ε = 1e-6 floating-point tolerance).

9. **`find_owners` round-trip.** After a successful run, the MCP tool
   returns `top_n` owners ranked by `weight` for any file in
   `:File`; `total_authors` matches the count of `:OWNED_BY` edges
   for that file; `last_run_at` and `head_sha` match the most
   recent successful `:OwnershipRun`.

10. **Crash recovery is consistent.** A monkeypatched failure
    between Phase 3 and Phase 4 leaves checkpoint untouched; next
    re-run recomputes DIRTY identically; atomic-replace wipes any
    partial `:OWNED_BY` edges from the failed attempt; final state
    indistinguishable from a single successful run.

11. **`alpha_used` provenance.** Edges record the α value used at
    write time. Changing `PALACE_OWNERSHIP_BLAME_WEIGHT` between
    runs and re-running on the same DIRTY set rewrites edges with
    the new `alpha_used`.

12. **Single-author file.** A file authored entirely by one
    non-bot author has exactly one `:OWNED_BY` edge with
    `weight = 1.0`, `blame_share = 1.0`, `recency_churn_share = 1.0`.

13. **Empty DIRTY ⇒ exit shortcut.** When `last_head_sha == HEAD`
    AND graph state is consistent, extractor returns success with
    `dirty_files_count=0, edges_written=0` without holding a
    write tx.

14. **Schema bootstrap idempotent.** Two consecutive runs do not
    raise on constraint creation; `ensure_ownership_schema` uses
    `IF NOT EXISTS`.

## 10. Test plan

### 10.1 Unit (mock driver, fast)

| File | Scope |
|------|-------|
| `tests/extractors/unit/test_code_ownership_mailmap.py` | `.mailmap` parser; canonicalize() over 5+ syntax variants from git docs; missing-mailmap fallback |
| `tests/extractors/unit/test_code_ownership_scorer.py` | `α × blame + (1-α) × churn` formula edges (α=0, α=1); per-file normalization; single-author = 1.0; empty inputs |
| `tests/extractors/unit/test_code_ownership_churn_aggregator.py` | Cypher fragment shape on mock driver; merge/bot filtering; decay formula sanity checks |
| `tests/extractors/unit/test_code_ownership_blame_walker.py` | `pygit2.blame` over an in-process tmpdir mini-repo (3 commits, 2 authors, 1 file); binary skip; symlink skip |
| `tests/extractors/unit/test_code_ownership_checkpoint.py` | read/write/init `:OwnershipCheckpoint`; first-run NULL handling |
| `tests/extractors/unit/test_code_ownership_neo4j_writer.py` | atomic-replace tx Cypher on mock driver; DIRTY+DELETED merge into single tx |

### 10.2 Integration (real Neo4j via testcontainers)

`tests/extractors/integration/test_code_ownership_integration.py` against
new fixture `tests/extractors/fixtures/code-ownership-mini-project/`:

- 3 authors: one with two email aliases (in `.mailmap`), one bot, one human plain
- 5 files: one renamed once, one deleted in HEAD, one merge-only changed
- 12 commits including one merge
- `.mailmap` mapping `old@x.com → new@y.com`
- `REGEN.md` with reproducible creation script

Scenarios:

1. **Bootstrap full walk** — fresh run, no checkpoint → all expected
   `:OWNED_BY` edges emitted with normalized shares.
2. **No-op re-run** — second run on same HEAD → 0 edges written/deleted.
3. **Incremental edit** — append a commit changing one file → DIRTY
   set = {that file}; non-DIRTY edges keep their `run_id_provenance`.
4. **Deletion** — append a commit `git rm`-ing a file → DELETED set
   purges old edges for that path.
5. **Mailmap dedup** — verify two-email author resolves to one
   `:OWNED_BY` edge with summed `lines_attributed`.
6. **Bot exclusion** — bot author has zero `:OWNED_BY` edges anywhere.
7. **Merge exclusion** — merger does not accumulate
   `recency_churn_share` for files merged from the side branch.
8. **Crash recovery** — monkeypatch raise mid-Phase-3 → checkpoint
   intact → re-run produces clean state.

### 10.3 Wire-contract (MCP tool)

`tests/code/test_find_owners_wire.py`:

- success envelope shape (`top_n=1`, `top_n=5`, `top_n=100`)
- explicit `error_code == "unknown_file"`, `error_code ==
  "project_not_registered"`, `error_code ==
  "ownership_not_indexed_yet"`, `error_code == "slug_invalid"`,
  `error_code == "top_n_out_of_range"` (per
  `feedback_wire_test_tautological_assertions.md` — assert on the
  string value, not on `isError` flag).

### 10.4 Smoke (live, on iMac)

`tests/extractors/smoke/test_code_ownership_smoke.sh`:
- runs extractor against `gimle` (palace-mcp itself, dogfood).
- queries `find_owners` for a known file
  (e.g. `services/palace-mcp/src/palace_mcp/extractors/foundation/importance.py`)
  and validates: `len(owners) ≥ 1`, top owner `author_email` is the
  expected human, `weight ∈ (0, 1]`, `total_authors > 1`.

### 10.5 Coverage matrix (Phase 3.1 CR — per `feedback_silent_scope_reduction`)

| Component | Unit | Integration | Wire | Smoke |
|-----------|:----:|:-----------:|:----:|:-----:|
| `mailmap.py` | ✅ | ✅ | — | — |
| `blame_walker.py` | ✅ | ✅ | — | ✅ |
| `churn_aggregator.py` | ✅ | ✅ | — | ✅ |
| `scorer.py` | ✅ | ✅ | — | — |
| `checkpoint.py` | ✅ | ✅ | — | — |
| `neo4j_writer.py` | ✅ | ✅ | — | — |
| `extractor.py` orchestrator | — | ✅ (8 scenarios) | — | ✅ |
| `find_owners.py` MCP tool | — | ✅ | ✅ | ✅ |

## 11. Operator workflow (CLAUDE.md addition)

```
### Operator workflow: Code ownership

Prereq: GIM-186 git_history extractor must have run for the project
(`palace.memory.lookup` shows `:Commit` count > 0).

1. Run the extractor:
   palace.ingest.run_extractor(name="code_ownership", project="gimle")
2. Query owners:
   palace.code.find_owners(file_path="services/...", project="gimle", top_n=5)

Optional: place `.mailmap` in the repo root to dedupe split identities
(standard git format — see `git help check-mailmap`).

Tunable knobs (`.env`):
- PALACE_OWNERSHIP_BLAME_WEIGHT (default 0.5) — α in scoring formula
- PALACE_OWNERSHIP_MAX_FILES_PER_RUN (default 50000)

Limitations:
- File renames lose history pre-rename (pygit2 blame is path-bound)
- Submodules and binary files are skipped
- Bundle support is not yet wired (run per-project for HS Kits)
```

## 12. Documentation deliverables

- `docs/runbooks/code-ownership.md` — operator runbook (env vars,
  troubleshooting, mailmap recipes).
- `CLAUDE.md ## Extractors` — register `code_ownership` row + add the
  workflow block above.
- `docs/superpowers/plans/2026-05-06-GIM-NN-code-ownership-extractor.md`
  — TDD plan (immediate next deliverable in this same Board+Claude
  session).

## 13. Out-of-scope cleanups (NOT in this slice)

Listed for future memory; not blocking this slice:

- Add LOC delta to `:TOUCHED` in `git_history` writer — F8 prereq.
- Bundle-aware async run pattern — F3 (mirror GIM-182 design).
- Symbol-level ownership bridge — F1 (depends on harmonized
  symbol-index DEF spans across languages).

## 14. Risks

| Risk | Mitigation |
|------|------------|
| `pygit2.blame` slow on huge files (>10k LOC) | Per-file timeout policy in `blame_walker.py`: log warn, skip; aggregate skipped count in `:OwnershipRun`. Document threshold (`PALACE_OWNERSHIP_BLAME_TIMEOUT_S` if needed — defer until measured). |
| `.mailmap` parsing edge cases | pygit2 native API is the upstream-preferred path; if it bugs out, fall back to identity passthrough with `mailmap_parse_error` warn. Do not implement own parser. |
| GIM-186 schema evolution may rename `:Commit.is_merge` semantics | Acceptance #7 covers this; drift caught at integration test time, not in production. |
| α tuning unclear without data | `alpha_used` provenance lets us A/B retroactively. Followup tuning slice if v1 yields complaints. |

---
