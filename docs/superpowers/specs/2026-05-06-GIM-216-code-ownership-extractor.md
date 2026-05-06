---
title: Code ownership extractor — file-level blame_share + recency-weighted churn
slug: code-ownership-extractor
date: 2026-05-06
status: proposed (rev2)
paperclip_issue: GIM-216
predecessor_sha: 0a9c2363a
authoring: Board+Claude
team: Claude
roadmap_item: "#32 Code Ownership Extractor"
roadmap_source: "docs/roadmap.md §2.3 Historical, row #32 (verified 2026-05-06 by Board+Claude after GIM-195 hotspot merged)"
---

# Code ownership extractor (Roadmap #32)

## rev2 changelog (2026-05-06)

Operator pre-CR review across 4 independent agents (Architect / Security
/ Silent-failure / Performance) surfaced one correctness bug + 17
material gaps. Rev2 closes all 18:

- **C1 (correctness, Performance Risk 1)** — Phase 4 DELETE filter
  `r.run_id_provenance = 'extractor.code_ownership'` was unmatched after
  first run because `run_id_provenance` is a per-run UUID. Added stable
  `r.source = 'extractor.code_ownership'` for filtering;
  `run_id_provenance` retained as UUID audit trail.
- **C2 (atomicity, Architect + Silent + Performance Risk 3)** — Phase 4
  pseudocode `;` was misleading. Now explicit
  `async with session.begin_transaction() as tx` with batched DELETE+MERGE
  by `PALACE_OWNERSHIP_WRITE_BATCH_SIZE` (default 2000 paths). Per-batch
  atomic contract: a file's old edges are deleted + new edges written
  in one tx → readers always see consistent per-file ownership.
- **C3 (mailmap, Architect + Security F2 + Silent)** — dropped custom
  parser. v1 uses **only** `pygit2.Mailmap.from_repository(repo)` if the
  bound libgit2 exposes it; else identity-passthrough fallback (no
  parser). Bounds: `PALACE_MAILMAP_MAX_BYTES=1_048_576` (1 MiB);
  oversized → `mailmap_unsupported` log + identity passthrough. Resolver
  path logged as `:IngestRun.mailmap_resolver_path ∈ {'pygit2',
  'identity_passthrough'}`.
- **C4 (find_owners empty-state, Silent HIGH)** — added `:OwnershipFileState`
  sidecar node `(project_id, path)` with `status ∈ {processed, skipped}`
  and `no_owners_reason ∈ {binary_or_skipped, all_bot_authors,
  no_commit_history, file_not_yet_processed}`. `find_owners` exposes
  `no_owners_reason` and `last_run_id` so caller distinguishes
  "no humans" from "not yet processed".
- **C5 (synthetic flag, Architect + Silent MED)** — moved `_synthetic_from_mailmap`
  off `:Author` (where ON CREATE only fired). New per-edge property
  `r.canonical_via ∈ {'identity', 'mailmap_existing', 'mailmap_synthetic'}`
  set on every write; provenance stays accurate across re-runs.
- **C6 (dead index, Architect + Performance)** — removed
  `file_owned_by_weight` relationship-property index. `find_owners`
  uses `:File` PK lookup + outgoing expand + in-memory sort; the index
  helps full-scans, not traversals from a starting node.
- **C7 (Phase 3 perf, Performance Risk 2)** — reversed query direction:
  `MATCH (f:File {project_id, path})<-[:TOUCHED]-(c:Commit)` uses File
  PK index; partial server-side aggregation by `a.identity_key` returns
  collected `committed_at` timestamps + counts, ~3 orders of magnitude
  faster than client-pulling raw rows.
- **C8 (substrate alignment, Architect C1)** — dropped duplicate
  `:OwnershipRun` label (rev1 design). Now writes `(:IngestRun {source:
  'extractor.code_ownership', ...substrate fields, ...ownership extras})`.
  Honors CLAUDE.md `palace.memory.lookup(entity_type='IngestRun',
  filters={source: 'extractor.<name>'})` contract. `:OwnershipCheckpoint`
  retained as per-extractor label (mirrors GIM-186
  `:GitHistoryCheckpoint` precedent).
- **C9 (decision-log honesty, Architect)** — R5 reworded: α=0.5 is a
  neutral start without empirical validation; tunable env-var lets
  operators A/B retroactively via `alpha_used` provenance. R7
  reworded: 5-15 min is an estimate; concrete number TBD during
  plan-validation phase on UW Android fixture.
- **C10 (bot prefetch scoping, Security F4)** — bot prefetch query
  rewritten to project-scope via `:Commit{project_id}` join + `LIMIT
  10000` defensive cap.
- **C11 (PII redaction, Security F6)** — explicit invariant in §8:
  `error_message` and INFO logs MUST NOT contain raw email addresses.
  `mailmap_unsupported` and `blame_failed` warnings reference paths,
  not authors.
- **C12 (privacy / PII, Security F7)** — new §15 Privacy: PII inventory,
  erasure Cypher template (`MATCH (a:Author{identity_key:$email})
  DETACH DELETE a` + downstream `:OWNED_BY` cleanup), retention
  guidance, runbook reference.
- **C13 (bot-laundering, Security F5)** — new §14 risk row + runbook
  spot-check guidance.
- **C14 (trust model, Security F1)** — §1 expanded with explicit
  trust-model statement: ownership data is more PII-sensitive than
  symbol queries; project-level ACL is a separate palace-mcp slice
  (not blocking #32). Operators with multi-tenant deployments must
  treat `find_owners` as PII-bearing.
- **C15 (substrate caps clarification, Performance)** — §6 note: the
  Tantivy-related substrate caps (`PALACE_MAX_OCCURRENCES_*`) do NOT
  apply to code_ownership (no Tantivy writes).
- **C16 (find_owners SLO, Performance)** — added p99 < 50 ms target
  for warm cache after bootstrap; documented as soft contract verified
  by integration test on bootstrapped fixture.
- **C17 (new error codes, Silent)** — added `ownership_diff_failed`
  (pygit2.Diff between checkpoint and HEAD raises),
  `repo_head_invalid` (pygit2 cannot resolve HEAD); `:IngestRun.exit_reason`
  enum: `'success' | 'no_change' | 'no_dirty' | 'failed'`. Replaces the
  `head_unchanged_no_dirty` informational pseudo-code.
- **C18 (acceptance #15-17)** — explicit acceptance for atomicity
  contract (kill simulation between batches), substrate `:IngestRun`
  visibility via `palace.memory.lookup`, and `find_owners` empty-state
  disambiguation.

**Skipped (operator triage)**: `PALACE_OWNERSHIP_PROJECT_ALLOWLIST`
(broader palace-mcp ACL, not #32); per-file blame timeout (defer until
measured); `bot_classification_drift` (vague — GIM-186 heuristic is
non-deterministic by design); `mailmap_resolver_disagreement` (moot
after C3); `mailmap_drift_detected` (next full re-walk auto-corrects);
`extractor_tx_atomicity_violation` (internal assert, not error code);
`ownership_checkpoint_orphaned` (self-healing); intermediate blame
checkpoint (premature); per-file edge-count cap (top_n covers it).

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
last_touched_at)` with provenance metadata `(last_run_at, total_authors,
no_owners_reason)`.

**Trust model (PII sensitivity).** Ownership data exposes raw committer
emails and blame attribution — strictly more PII-bearing than symbol
queries. Operators running palace-mcp in multi-tenant deployments MUST
treat `find_owners` as PII-bearing: any caller with `palace.code.*`
permissions can enumerate every contributor's email for any registered
project. Project-level ACLs are not implemented in palace-mcp v1
(broader slice; not blocking #32). Single-tenant or trusted-team
deployments can run as-is. This is documented in `docs/runbooks/code-ownership.md`
under "Trust assumptions".

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
  `extractors/code_ownership/mailmap.py`. **v1 single source: `pygit2.Mailmap.from_repository(repo)`**.
  If the bound libgit2 does not expose this API, OR if `.mailmap` exceeds
  `PALACE_MAILMAP_MAX_BYTES` (1 MiB default), OR if pygit2 raises during
  parse → fall back to **identity passthrough** (`canonicalize(name,
  email) = (name, email.lower())`). No custom parser. The resolver path
  used (`'pygit2' | 'identity_passthrough'`) is logged once at run-start
  and recorded as `:IngestRun.mailmap_resolver_path` for reproducibility.
  Rationale: `.mailmap` is checked-in repo content (untrusted); pygit2 is
  the upstream-vetted parser. A second in-house parser would split test
  surface and is the wrong attack-surface trade-off.
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

- **R3 (identity) — `.mailmap`-aware via pygit2; no custom parser, no
  heuristic merge.** UW history spans 2017-2026; multiple email-per-person
  is real. `.mailmap` is the standard git solution. v1 uses
  `pygit2.Mailmap.from_repository(repo)` exclusively; absence /
  oversized / pygit2-unsupported → identity passthrough (no custom
  parser; `.mailmap` is untrusted repo content). Heuristic merge (F5)
  risks false-positive cross-author merges and is deferred. **Edge
  case — synthetic canonical email**: if `.mailmap` rewrites to an
  email never used in any commit (rare), Phase 4 MERGEs a synthetic
  `:Author{provider:'git', identity_key: canonical_email_lc}` and
  records `r.canonical_via='mailmap_synthetic'` on the edge. Documented
  in §4 Phase 4.

- **R4 (MCP surface) — single tool: `find_owners`.** Symmetric with
  #44's `find_hotspots`. Orphan-files / module-owners are followups
  (F6/F7) with their own tuning knobs.

- **R5 (scoring) — `α × blame + (1-α) × churn`, α=0.5 default.** Two
  sub-questions ("who wrote it" vs "who maintains it") both matter; we
  start at α=0.5 as a **neutral midpoint without empirical
  validation** — there is no UW data yet to tune against. Env-tunable
  `PALACE_OWNERSHIP_BLAME_WEIGHT` lets operators retune; per-edge
  `alpha_used` provenance enables retroactive A/B comparison once we
  have real query traffic. A tuning slice (with measured signal-quality
  metrics) is a possible followup if α=0.5 produces complaints.

- **R6 (scope) — single-project per run.** Symmetric with #44 and
  #5 (dependency_surface). Bundle support (F3) is structurally
  identical to GIM-182 multi-repo SPM ingest; can be lifted later.

- **R7 (incrementality) — per-file incremental with checkpoint.** UW
  Android (~3k Kotlin/Java files in HEAD) full blame walk is the
  bootstrap cost; **wall-time TBD — to be measured during plan
  validation phase**, not asserted here. Whatever the measured
  bootstrap cost, per-merge incremental refresh on the typical
  10-50-file diff converges to seconds (one Phase-2 blame call per
  changed file). The checkpoint pattern preserves bootstrap cost as
  one-time and shrinks the steady-state cost to per-merge size.

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
        for row in MATCH (c:Commit {project_id: $proj})
                         -[:AUTHORED_BY]->(a:Author)
                   WHERE a.is_bot = true
                   RETURN DISTINCT a.identity_key
                   LIMIT 10000}
    // project-scoped (Author is global per GIM-186 schema, so bot
    // detection is shared across projects, but we want only bots that
    // actually appear in this project's commit graph).
    // LIMIT 10000 is defensive; typical projects have 1–5 bots.
  • mailmap_resolver_path = "pygit2" if pygit2.Mailmap exposed
                             AND .mailmap size ≤ PALACE_MAILMAP_MAX_BYTES
                             else "identity_passthrough"
  • known_author_ids = {row.identity_key
        for row in MATCH (c:Commit {project_id: $proj})
                         -[:AUTHORED_BY]->(a:Author)
                   RETURN DISTINCT a.identity_key}
    // used by Phase 3/4 to set r.canonical_via:
    //   'identity'           if raw_id == canonical_id
    //   'mailmap_existing'   if canonical_id in known_author_ids
    //   'mailmap_synthetic'  otherwise (need to MERGE virtual :Author)
  • read repo HEAD via pygit2; on failure → repo_head_invalid
  • assert there is at least one :Commit{project_id} in graph else
    fail with git_history_not_indexed

Phase 1 — DIRTY/DELETED set computation
  • current_head = repo.head.target.hex
  • if checkpoint.last_head_sha is None:
      DIRTY = all files in repo.head.peel().tree (recursive)
      DELETED = ∅
      exit_reason = (pending; set after Phase 4)
  • else if last_head_sha == current_head:
      → exit_reason = "no_change"; success no-op
        (checkpoint untouched, :IngestRun written for audit)
  • else:
      try diff = repo.diff(last_head_sha, current_head)
      except pygit2.GitError → fail with ownership_diff_failed
        (operator likely needs to git fetch / repair the mounted clone)
      DIRTY = paths with delta.status ∈ {ADDED, MODIFIED, RENAMED}
              (RENAMED: NEW path enters DIRTY; OLD path enters DELETED)
      DELETED = paths with delta.status == DELETED
  • assert len(DIRTY) ≤ PALACE_OWNERSHIP_MAX_FILES_PER_RUN
    else fail with ownership_max_files_exceeded
  • if DIRTY = ∅ and DELETED = ∅ (e.g., only commits to non-text
    binaries that DELETED-pass through but blame fails uniformly):
      exit_reason = "no_dirty"; same shortcut as no_change

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
  // Query starts from :File (PK lookup via UNIQUE(project_id, path)
  // index from GIM-186) — orders of magnitude faster than starting
  // from :Commit (which has no project_id index, would full-scan).
  // Server-side preliminary aggregation by raw_id (a.identity_key)
  // collapses N rows-per-author down to 1 row-per-author per file.
  // Mailmap canonicalize is unavoidably client-side; we still aggregate
  // a second pass over the canonical key after mailmap.
  • UNWIND $dirty_paths AS p
    MATCH (f:File {project_id: $proj, path: p})<-[:TOUCHED]-(c:Commit)
    WHERE NOT c.is_merge
    MATCH (c)-[:AUTHORED_BY]->(a:Author)
    WHERE NOT a.is_bot
    WITH p, a.identity_key AS raw_id, a.name AS raw_name,
         collect(c.committed_at) AS timestamps
    RETURN p, raw_id, raw_name,
           timestamps,
           size(timestamps) AS commit_count
  • client-side per row:
      (canonical_name, canonical_email) = mailmap.canonicalize(raw_name, raw_id)
      canonical_id = canonical_email.lower()
      if canonical_id in bot_identity_keys: continue  // post-mailmap bot check
      decay_seconds = decay_days × 86400
      recency_score = Σ exp(-(now - ts).total_seconds() / decay_seconds)
                      for ts in timestamps
      last_touched_at = max(timestamps)
      // Second-pass merge per canonical_id (mailmap may collapse two raw_ids):
      churn_per_file[p][canonical_id].recency_score += recency_score
      churn_per_file[p][canonical_id].commit_count  += commit_count
      churn_per_file[p][canonical_id].last_touched_at = max(...)
      churn_per_file[p][canonical_id].canonical_via = (
          'identity'             if (raw_id == canonical_id)
          else 'mailmap_existing' if (canonical_id in :Author identity keys
                                       — pre-fetched in Phase 0)
          else 'mailmap_synthetic'
      )
  • result: dict[path, dict[canonical_id, ChurnShare(...)]]

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
  • Atomic-replace contract: per-batch (NOT per-run). Within one tx,
    a batch's DIRTY+DELETED paths' old :OWNED_BY edges are removed and
    new edges written. Readers querying a path covered by batch N see
    either the pre-batch-N state or the post-batch-N state, never a
    mixed state. Across batches, eventual consistency: the per-file
    contract is what matters.
  • Pseudocode:
      batches = chunk(dirty_paths + deleted_paths,
                      size=PALACE_OWNERSHIP_WRITE_BATCH_SIZE)
      for batch_paths, batch_edges in batches:
          async with session.begin_transaction() as tx:
              # 1. Wipe old edges for ALL batch paths (DIRTY + DELETED).
              #    Filter by stable r.source — the per-run UUID is
              #    in r.run_id_provenance, NOT here.
              await tx.run("""
                  UNWIND $paths AS p
                  MATCH (f:File {project_id: $proj, path: p})
                        -[r:OWNED_BY {source: 'extractor.code_ownership'}]
                        ->()
                  DELETE r
              """, paths=batch_paths, proj=project_id)

              # 2. Write new edges for the DIRTY paths in this batch
              #    (DELETED paths have no corresponding e in batch_edges).
              #    MERGE author on canonical: handles synthetic mailmap
              #    targets. For non-synthetic, idempotent.
              await tx.run("""
                  UNWIND $edges AS e
                  MATCH (f:File {project_id: $proj, path: e.path})
                  MERGE (a:Author {provider: 'git',
                                   identity_key: e.canonical_id})
                    ON CREATE SET a.email = e.canonical_email,
                                  a.name = e.canonical_name,
                                  a.is_bot = false,
                                  a.first_seen_at = e.last_touched_at,
                                  a.last_seen_at = e.last_touched_at
                  MERGE (f)-[r:OWNED_BY]->(a)
                  SET r.source = 'extractor.code_ownership',
                      r.weight = e.weight,
                      r.blame_share = e.blame_share,
                      r.recency_churn_share = e.recency_churn_share,
                      r.last_touched_at = e.last_touched_at,
                      r.lines_attributed = e.lines_attributed,
                      r.commit_count = e.commit_count,
                      r.run_id_provenance = $run_id,
                      r.alpha_used = $alpha,
                      r.canonical_via = e.canonical_via
              """, edges=batch_edges, proj=project_id,
                   run_id=run_id, alpha=alpha)

              # 3. Sidecar :OwnershipFileState for empty-state
              #    disambiguation in find_owners.
              await tx.run("""
                  UNWIND $states AS s
                  MERGE (st:OwnershipFileState {project_id: $proj,
                                                path: s.path})
                  SET st.status = s.status,
                      st.no_owners_reason = s.no_owners_reason,
                      st.last_run_id = $run_id,
                      st.updated_at = $now
              """, states=batch_states, proj=project_id,
                   run_id=run_id, now=now)
              # tx auto-commits on context exit
  • after all batches commit:
      update :OwnershipCheckpoint{last_head_sha=current_head,
                                   last_completed_at=NOW(),
                                   run_id=$run_id}
      write :IngestRun {source: 'extractor.code_ownership',
                        ...substrate fields,
                        head_sha, prev_head_sha,
                        dirty_files_count, deleted_files_count,
                        edges_written, edges_deleted,
                        mailmap_resolver_path,
                        exit_reason: 'success'}

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

**`:IngestRun`** (substrate; append-only; one per ownership run)

We do NOT introduce a separate `:OwnershipRun` label (rev1 had one;
rev2 dropped it). Per CLAUDE.md
extractor convention (`palace.memory.lookup(entity_type='IngestRun',
filters={source: 'extractor.<name>'})`), all extractor runs write to
the substrate `:IngestRun`. We add ownership-specific properties on
the same node; substrate properties unchanged.

Substrate properties (from `foundation/checkpoint.py:create_ingest_run`):
`run_id` (UUID, PK), `project_id`, `source`, `started_at`,
`completed_at`, `success`, `nodes_written`, `edges_written`,
`error_code`, `error_message`, `duration_ms`.

Ownership-extension properties (set by this extractor only):

| Property | Type | Note |
|----------|------|------|
| `head_sha` | string | target HEAD of run |
| `prev_head_sha` | string \| null | for diff-tracing |
| `dirty_files_count` | int | files re-blamed |
| `deleted_files_count` | int | files removed in HEAD |
| `edges_deleted` | int | old `:OWNED_BY` removed |
| `mailmap_resolver_path` | string | `'pygit2' \| 'identity_passthrough'` |
| `exit_reason` | string | `'success' \| 'no_change' \| 'no_dirty' \| 'failed'` |

For `source = "extractor.code_ownership"`. Substrate's UNIQUE constraint
on `:IngestRun.run_id` is reused; no new constraint needed.

**`:OwnershipFileState`** (one per `(project_id, path)` for files
seen by ownership; sidecar for empty-state disambiguation in
`find_owners`)

| Property | Type | Note |
|----------|------|------|
| `project_id` | string | composite PK part 1 |
| `path` | string | composite PK part 2 |
| `status` | string | `'processed' \| 'skipped'` |
| `no_owners_reason` | string \| null | `'binary_or_skipped' \| 'all_bot_authors' \| 'no_commit_history' \| null` (null when status='processed' AND `:OWNED_BY` edges exist) |
| `last_run_id` | string (UUID) | run that last touched this state |
| `updated_at` | datetime (UTC) | |

`CREATE CONSTRAINT ownership_file_state_unique IF NOT EXISTS FOR (s:OwnershipFileState) REQUIRE (s.project_id, s.path) IS UNIQUE;`

A `:File` that has NO `:OwnershipFileState` was never DIRTY in any
ownership run → `find_owners` returns
`no_owners_reason='file_not_yet_processed'`.

### New edge

**`(:File)-[:OWNED_BY]->(:Author)`**

| Property | Type | Note |
|----------|------|------|
| `source` | string | stable filter key, hardcoded `"extractor.code_ownership"`; used by Phase 4 DELETE filter |
| `weight` | float [0..1] | combined score |
| `blame_share` | float [0..1] | line-share in HEAD blame |
| `recency_churn_share` | float [0..1] | decay-weighted commit-share |
| `last_touched_at` | datetime | max committed_at by this author on this file |
| `lines_attributed` | int | absolute blame line count |
| `commit_count` | int | absolute commit count (no decay) |
| `run_id_provenance` | string (UUID) | run that wrote the edge (audit trail; UUID, not stable filter key) |
| `alpha_used` | float | α at write time |
| `canonical_via` | string | `'identity' \| 'mailmap_existing' \| 'mailmap_synthetic'` — how `:Author.identity_key` was reached |

Cardinality: one edge per `(File, Author)` per project (enforced by
`MATCH (f) MATCH (a) MERGE (f)-[r:OWNED_BY]->(a)`).

**No relationship-property index.** `find_owners` uses `:File` PK
lookup → outgoing `:OWNED_BY` traversal → in-memory sort by
`r.weight` over the small per-file owner set (typically ≤ 20).
A relationship-property index would only help full-scan predicates,
not traversals from a starting node. Indexing the property would
just add write cost on every MERGE without speeding up the read path.

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
| `PALACE_OWNERSHIP_WRITE_BATCH_SIZE` | `2000` | paths per Phase-4 atomic-replace tx; range `[100, 10000]` enforced |
| `PALACE_MAILMAP_MAX_BYTES` | `1048576` (1 MiB) | upper bound for `.mailmap` file; oversized → `mailmap_unsupported` log + identity passthrough |

Reused from substrate (no change):
- `PALACE_RECENCY_DECAY_DAYS = 30` — half-life for `exp(-Δdays/T)`

**Substrate caps that do NOT apply to this extractor:**
- `PALACE_MAX_OCCURRENCES_TOTAL`, `PALACE_MAX_OCCURRENCES_PER_PROJECT`,
  `PALACE_MAX_OCCURRENCES_PER_SYMBOL` — these gate Tantivy occurrence
  writes; ownership extractor does NOT write to Tantivy.
- `PALACE_TANTIVY_*` — same reason.
- `PALACE_IMPORTANCE_THRESHOLD_USE` — substrate eviction gate; not
  invoked for ownership data.

`check_phase_budget()` is still called at the start of each phase per
substrate convention, but its node/edge cap inputs reflect ownership-
specific counters (DIRTY size, edges_written), not Tantivy occurrences.

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
            "canonical_via": "identity",   # or 'mailmap_existing' | 'mailmap_synthetic'
        },
        # ...
    ],
    "total_authors": 14,           # before top_n filter
    "no_owners_reason": null,      # set when owners is empty (see below)
    "last_run_id": "uuid-...",     # :OwnershipFileState.last_run_id
    "last_run_at": "2026-05-06T08:30:11Z",
    "head_sha": "0a9c2363a39b94f14e5bcdc5e3db44233c8a349c",
    "alpha_used": 0.5,
}
```

**Empty-owners disambiguation.** When `owners=[]` and `total_authors=0`,
`no_owners_reason` is one of:

| Value | Meaning |
|-------|---------|
| `"binary_or_skipped"` | blame_walker raised on this path (binary, symlink, submodule) |
| `"all_bot_authors"` | all blame attributions resolve to bot identities |
| `"no_commit_history"` | `:File` exists but no `:TOUCHED` history (rare; possible if GIM-186 is partial) AND blame produced no humans |
| `"file_not_yet_processed"` | `:File` exists but no `:OwnershipFileState` — the file has not been DIRTY in any run since the extractor started running. Caller should re-run the extractor. |

**Performance SLO (soft).** For a project that has a successful
bootstrap run on file in `:File` graph with `:OwnershipFileState`
already populated: `find_owners` p99 latency target < 50 ms (warm
Neo4j cache, top_n ≤ 20). Verified by integration test on the
mini-fixture; CI failure threshold = p99 > 200 ms (loose to avoid
flake). Production deviation is a follow-up perf investigation, not
a hard merge gate.

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
   `ownership_not_indexed_yet` (extractor was never run for this
   project).
4. check `(:File {project_id: $slug, path: $file_path})` exists —
   fail `unknown_file` if not.
5. fetch `:OwnershipFileState {project_id, path}` and `:OWNED_BY`
   edges in one query:
   ```cypher
   MATCH (f:File {project_id: $slug, path: $file_path})
   OPTIONAL MATCH (st:OwnershipFileState {project_id: $slug, path: $file_path})
   OPTIONAL MATCH (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
   WITH st, collect({r: r, a: a}) AS owner_rows
   RETURN st, owner_rows
   ```
6. Compose response based on the join:
   - `owner_rows` non-empty → success with sorted top_n owners,
     `no_owners_reason=null`.
   - `owner_rows` empty AND `st` not null → success-empty with
     `no_owners_reason = st.no_owners_reason`,
     `last_run_id = st.last_run_id`.
   - `owner_rows` empty AND `st` is null → success-empty with
     `no_owners_reason = "file_not_yet_processed"`,
     `last_run_id = null`. Caller should re-run extractor; the file
     was added to `:File` (e.g., by GIM-186 walking a new commit) but
     the ownership extractor has not yet had it in a DIRTY set.

## 8. Error handling and idempotency

### `ExtractorErrorCode` additions (in `foundation/errors.py`)

| Code | When |
|------|------|
| `ownership_max_files_exceeded` | DIRTY > `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` |
| `git_history_not_indexed` | `count((c:Commit{project_id:$slug}))` = 0 |
| `ownership_diff_failed` | `pygit2.Repository.diff(last_head_sha, current_head)` raises (corrupt local clone, fetch needed); fail-fast with the SHA pair in `error_message` |
| `repo_head_invalid` | `pygit2.Repository(path).head` raises (detached HEAD with no fetch, corrupt refs) |
| `mailmap_unsupported` | log-level info, NOT a run-failure code: pygit2.Mailmap unavailable OR `.mailmap` exceeds `PALACE_MAILMAP_MAX_BYTES` OR pygit2 raises while reading; resolver falls back to identity passthrough |
| `blame_failed` | per-file warning only — NOT a run-failure code; aggregated count goes to `:IngestRun.error_message` summary if non-zero (path-only, NEVER author email) |

Existing substrate codes used as-is: `repo_not_mounted`,
`project_not_registered`, `extractor_config_error`,
`extractor_runtime_error`.

`:IngestRun.exit_reason` enum (replaces the rev1
`head_unchanged_no_dirty` informational pseudo-code):

| Value | Meaning |
|-------|---------|
| `success` | run completed and at least one batch wrote edges |
| `no_change` | `last_head_sha == current_head` shortcut taken |
| `no_dirty` | DIRTY ∪ DELETED = ∅ (rare; e.g., commits only changed binary files) |
| `failed` | run aborted; `error_code` and `error_message` populated |

### PII / email redaction (Security F6)

Invariant: **`error_message` and INFO-level logs MUST NOT contain raw
email addresses.** Mailmap and blame errors reference paths and SHAs,
not authors. The author identity exposed in `:Author.email` and
`:OWNED_BY` properties is the only authorized PII surface; logs and
error envelopes are NOT.

Audit-time check: a unit test scans the `extractors/code_ownership/`
package source for `f"... {email}"` / `f"... {a.email}"` style
log call-sites and fails CI on match (regex-based; conservative;
maintainers explicitly opt-in via `# noqa: PII` if a log call must
include an email — none should in v1).

### Idempotency invariants

1. **No-op re-run** — same HEAD, no DIRTY → 0 edges touched; new
   `:IngestRun{source='extractor.code_ownership'}` written for audit; checkpoint `last_completed_at`
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
   `:OwnershipCheckpoint` and `:IngestRun{source: 'extractor.code_ownership', success: true, exit_reason: 'success'}`; emits
   `:OWNED_BY` edges for every non-binary, non-submodule file.

2. **No-op re-run when HEAD unchanged.** Second run with identical
   HEAD writes 0 new edges, deletes 0 edges, but persists a new
   `:IngestRun{source='extractor.code_ownership'}` and advances `last_completed_at`.

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
   recent successful `:IngestRun{source='extractor.code_ownership'}`.

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

15. **Per-batch atomicity contract.** Integration test with
    `PALACE_OWNERSHIP_WRITE_BATCH_SIZE=1` (forces one batch per file),
    monkeypatched failure between batch 3 and batch 4. After re-run:
    files in batches 1-3 reflect the new HEAD state; files in batches
    4-N revert to old state via the next run's atomic-replace. No
    file is left in a "half-deleted, half-written" state. Verified by
    Cypher count: every `:File` in DIRTY has either zero `:OWNED_BY`
    edges (old wiped, new not yet written → next-run fixes) OR a
    fully consistent set with all required properties present.

16. **Substrate `:IngestRun` visibility.** `palace.memory.lookup(
    entity_type='IngestRun', filters={'source': 'extractor.code_ownership',
    'project_id': '<slug>'})` returns the most recent successful run
    with `exit_reason`, `head_sha`, `dirty_files_count`,
    `mailmap_resolver_path` populated. No `:OwnershipRun` label exists
    in the graph (rev1 design dropped in rev2).

17. **`find_owners` empty-state disambiguation.** For each empty-state
    case (binary, all-bot, no-history, file-not-yet-processed),
    `find_owners` returns `ok=True, owners=[], total_authors=0` AND a
    distinct `no_owners_reason` value. A file in `:File` not yet seen
    by ownership extractor → `"file_not_yet_processed"` (last_run_id
    is null). A binary file processed by ownership extractor →
    `"binary_or_skipped"` (last_run_id matches a real `:IngestRun`).

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
- `docs/superpowers/plans/2026-05-06-GIM-216-code-ownership-extractor.md`
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
| `pygit2.blame` slow on huge files (>10k LOC) | Per-file blame is bounded by file size, not history depth. Wall-time on UW Android files TBD during plan validation; if any file exceeds 30 s we add `PALACE_OWNERSHIP_BLAME_TIMEOUT_S` then. v1 ships without a hard timeout to surface real signal. |
| `.mailmap` is checked-in, untrusted content | pygit2 is the only parser; size-bounded by `PALACE_MAILMAP_MAX_BYTES`; oversized → identity passthrough. Resolver path logged on every run. |
| Bot-laundering via `git config user.name "github-actions[bot]"` | GIM-186 bot detection is heuristic. A human can spoof bot-name (or vice versa, an actual bot uses a human name). v1 trusts GIM-186's classification and documents the limitation in the operator runbook. Spot-check guidance: after bootstrap run, `palace.code.find_owners` for high-stake files; if a stranger appears, audit by querying their `:Commit` history. |
| Email leakage in error envelopes / logs | Hard rule: `error_message` and INFO logs MUST NOT contain raw emails (§8). Audited by a unit test that greps the package source. |
| Multi-tenant PII enumeration | `find_owners` enumerates committer emails of any registered project; project-level ACLs are not in scope here. Documented in §1 trust-model statement and `docs/runbooks/code-ownership.md`. |
| GIM-186 schema evolution (`:Commit.is_merge`, `:Author.is_bot`) | Acceptance #6/#7 cover the current contract; drift caught at integration test time. If GIM-186 changes semantics, ownership extractor updates in lockstep. |
| α tuning unclear without data | `alpha_used` provenance lets us A/B retroactively. Followup tuning slice if v1 yields complaints. |
| Long-tail authors (drive-by typo-fixes) inflate `total_authors` | `find_owners.top_n` filters; if operators want stricter cuts, add `min_weight` knob in v2. v1 ships unfiltered to preserve signal. |

## 15. Privacy / PII

### Inventory

| Surface | PII content | Source |
|---------|-------------|--------|
| `:Author.email` | raw committer email | GIM-186 (read-only here) |
| `:Author.name` | committer display name | GIM-186 (read-only here) |
| `(:File)-[:OWNED_BY]->(:Author)` traversal | "person X has touched file Y, with Z line attribution" | this extractor |
| `find_owners` response | enumerated emails per file | this extractor |
| `:IngestRun.error_message` | path / SHA only — NEVER email (enforced §8 invariant) | this extractor |
| `INFO log lines` | path / SHA only — NEVER email (enforced §8 invariant) | this extractor |
| `.mailmap` resolver state | parsed in-memory only; never serialized to graph | this extractor |

### Erasure (right-to-be-forgotten)

To erase author X's footprint after they exercise GDPR Art. 17 or
similar:

```cypher
// 1. Identify the canonical Author node.
MATCH (a:Author {provider: 'git', identity_key: $email_lc})
WITH a

// 2. Detach all :OWNED_BY edges sourced by ownership extractor.
//    (Author also has :AUTHORED_BY/:COMMITTED_BY from GIM-186 —
//    those need a separate erasure pass on :Commit if required.)
OPTIONAL MATCH (a)<-[r:OWNED_BY {source: 'extractor.code_ownership'}]-()
DELETE r

// 3. Optionally delete the Author node entirely if no other references.
//    WARNING: this also removes their git_history attribution.
WITH a
OPTIONAL MATCH (a)<-[any]-()
WITH a, count(any) AS remaining
WHERE remaining = 0
DELETE a
```

A cleaner flow: rewrite `:Author.email`/`:Author.name` to a tombstone
(e.g., `redacted-<hash>`) instead of deleting; keeps git-history graph
shape intact. Operator decides per request.

### Retention

`:Author` and `:OWNED_BY` accumulate indefinitely; v1 has no retention
sweep. Operators handling PII should run the erasure Cypher above on
demand. A retention-policy slice (TTL on `:Author.last_seen_at`,
automatic edge pruning) is a Phase 5 product candidate.

### Runbook reference

`docs/runbooks/code-ownership.md` mirrors this section operationally:
how to look up a person across `:Author.identity_key` (mailmap-aware),
how to apply the erasure Cypher safely, how to re-run the extractor
after a manual `:Author` rewrite.

---
