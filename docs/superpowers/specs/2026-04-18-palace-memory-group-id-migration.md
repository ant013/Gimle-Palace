# palace-memory — `group_id` migration (N+1-pivot)

**Status:** draft rev1 (Board) — 2026-04-18

**Supersedes:** N+1a Graphiti substrate swap (reverted as `a4abd28` on
2026-04-18; see `feedback_qa_skipped_gim48.md` memory entry for
post-mortem).

**Motivation:** After N+1a revert, an honest appraisal showed that
graphiti-core 0.4.3 does not support custom per-node attributes —
`EntityNode` has only `uuid`, `name`, `group_id`, `labels`,
`created_at`, `name_embedding`, `summary`. Hybrid scope (graphiti for
edges + raw Cypher for properties) would cost 2–3 days and return
~20% of the original N+1a value. The concrete unlock we need next is
**multi-project namespacing for N+1b** — and that requires only a
`group_id` column on existing N+0 nodes, not a substrate swap.

## 1. Goal

Add `group_id` as a first-class property on every `Issue`, `Comment`,
and `Agent` node, plus on every `IngestRun`, so that palace-memory can
partition data by project. Default `group_id = "project/gimle"` for
all existing rows. This directly unblocks N+1b multi-project.

## 2. Non-goals

- graphiti-core adoption (deferred to N+1c or later, when search
  becomes the driving need)
- bi-temporal `ASSIGNED_TO` (deferred — N+0 rewrite-on-each-upsert has
  lived 16 h in production without this)
- search / semantic queries
- cross-project `:BELONGS_TO_PROJECT` relations — `group_id` property
  + index is enough, no edges needed

## 3. Architecture

Same shape as N+0: raw parameterised Cypher against plain Neo4j 5.26,
ingest pipeline unchanged, lookup WHERE-clause whitelist extended.

### 3.1 Schema changes

- Every node in the ingest ontology gains property `group_id: str`.
- Existing `id IS UNIQUE` constraints **remain** (paperclip IDs are
  UUIDs — globally unique across projects).
- Add **index** `FOR (n:Issue) ON (n.group_id)`, and equivalents for
  `Comment`, `Agent`, `IngestRun`. Index (not unique constraint)
  because `group_id` is a namespace tag, not an identifier.

### 3.2 Write path (`ingest/cypher.py`)

- `UPSERT_AGENTS` / `UPSERT_ISSUES` / `UPSERT_COMMENTS` — add
  `{entity}.group_id = $group_id` in each `SET` clause. `group_id`
  supplied by the runner from config, not from paperclip row.
- `CREATE_INGEST_RUN` — add `group_id: $group_id` in the map.
- `GC_BY_LABEL` — extend WHERE to
  `n.source = 'paperclip' AND n.group_id = $group_id AND
  n.palace_last_seen_at < $cutoff`. GC now scoped to the ingest
  run's group; GC for other projects is untouched.

### 3.3 Read path (`memory/lookup.py`, `memory/filters.py`)

- Every lookup query gains an implicit `WHERE n.group_id = $group_id`
  clause (AND-ed with any explicit filter clauses). Parameter is
  supplied by the MCP tool implementation.
- MCP tool signature for `palace.memory.lookup` gains an optional
  `project: str | None` argument. `None` → use
  `settings.palace_default_group_id`. For N+1b, the tool will accept
  a list or "*", but that is **out of scope for this slice**.
- `LookupResponseItem.properties` does **not** expose `group_id` —
  callers who need it can ask with an explicit filter or a future
  projection field. Keeping the wire contract byte-stable is a hard
  requirement (§6).

### 3.4 Health

- `ENTITY_COUNTS` query remains label-scoped (no `group_id` filter by
  default), so `palace.memory.health()` returns **total** counts
  across all projects. A future slice may add per-project counts; not
  now.
- `LATEST_INGEST_RUN` gains optional `group_id` filter for the
  "latest per project" case — but the default call path (no project
  specified) returns the latest across all groups, preserving current
  behaviour.

### 3.5 Relationships and `group_id`

Edges (`ASSIGNED_TO`, `ON`, `AUTHORED_BY`) **do not** get their own
`group_id` property in this slice. They inherit namespace from the
connected nodes: a single ingest run always writes within one
`group_id`, so every edge it creates or deletes connects nodes in the
same group by construction.

Cross-project edge validation (rejecting an `ASSIGNED_TO` between an
Issue in `project/a` and an Agent in `project/b`) is **out of scope**
and becomes an N+1b concern when multiple projects actually coexist.

### 3.6 Config (`palace_mcp/config.py`)

- Add `palace_default_group_id: str = "project/gimle"` to
  `_EmbedderMixin` → inherited by `Settings` and `IngestSettings`.
- Environment variable name: `PALACE_DEFAULT_GROUP_ID`. Default
  preserves current single-project behaviour.

Renaming `_EmbedderMixin` is **out of scope** — leaving an
embedder-named mixin hosting a namespace field is a minor cosmetic
debt we accept to keep this slice narrow.

## 4. Backfill strategy

One-shot script at service startup (first run only):

```sql
-- Idempotent: only touches nodes that lack group_id
MATCH (n:Issue)   WHERE n.group_id IS NULL SET n.group_id = $default
MATCH (n:Comment) WHERE n.group_id IS NULL SET n.group_id = $default
MATCH (n:Agent)   WHERE n.group_id IS NULL SET n.group_id = $default
MATCH (n:IngestRun) WHERE n.group_id IS NULL SET n.group_id = $default
```

Runs inside `ensure_constraints()` (renamed `ensure_schema()` to
reflect the broader job — constraints + indexes + backfill). Safe
to re-run because the WHERE guard keeps it a no-op after the first
pass.

For the **existing production checkout** on iMac (34 Issues / 167
Comments / 12 Agents / N IngestRuns captured 2026-04-17), the
backfill runs once on first startup with the new code, stamps every
legacy row with `project/gimle`, and future upserts carry it
forward.

## 5. Backward compatibility

- `palace.memory.health()` response schema unchanged (counts stay
  label-scoped).
- `palace.memory.lookup` response schema unchanged — `group_id` is
  **not** added to the `properties` map. Internal WHERE-clause
  rewrite is invisible to callers using the default project.
- N+0 ingest CLI flag surface unchanged. The runner reads `group_id`
  from `IngestSettings.palace_default_group_id` automatically.
- Existing `.env` files on iMac continue to work — the new variable
  has a default matching the pre-migration reality.

## 6. Acceptance criteria

Hard gates, all must pass before merge:

- [ ] After running the service once against the existing iMac Neo4j,
      `MATCH (n) WHERE n.group_id IS NULL RETURN count(n)` returns
      `0`.
- [ ] A second ingest run completes without error and every node it
      touches carries `group_id = "project/gimle"`.
- [ ] `palace.memory.health()` via MCP returns the same counts as
      before migration (34 / 167 / 12 or newer actual numbers).
- [ ] `palace.memory.lookup(entity_type="Issue")` returns the same
      items as before (same `id`s, same order) — byte-identical
      response modulo `query_ms`.
- [ ] Index `EXISTS {INDEX issue_group_id}` etc. are present.
- [ ] Unit tests: filters produce `n.group_id = $group_id` clause for
      every entity type; GC query contains `n.group_id = $group_id`.
- [ ] CI green on all four jobs (**non-negotiable** — blocker for
      merge after GIM-48 gate-bypass lesson).
- [ ] QA Phase 4.1 live smoke on iMac — see plan `§4.1`. QAEngineer
      runs ingest CLI, verifies `MATCH (n) RETURN DISTINCT
      n.group_id` yields only `project/gimle`, captures the output in
      an evidence comment on the issue.

## 7. Out of scope, explicit

- Multi-project `project: list[str] | "*"` lookup semantics — N+1b.
- Project registry / `:Project` meta-nodes — N+1b.
- Cross-project queries in MCP tools — N+1b.
- Agent-side MCP + `record_note` — N+1c.
- graphiti-core adoption for search — future, post-N+1c.

## 8. Decomposition (spec-level — plan-file has bite-sized tasks)

Target agent: **MCPEngineer** (single-phase implementation, single
PR). Scope is too small to warrant multi-phase handoff.

- Phase 1.1 — CTO: formalize issue, confirm scope = this spec.
- Phase 1.2 — CTO + CodeReviewer: plan-first review of the plan-file.
- Phase 2 — MCPEngineer: TDD through plan-file tasks (est. 12 tasks /
  ~1 day).
- Phase 3.1 — CodeReviewer: mechanical review. **Must print output of
  `uv run ruff check && uv run mypy src/ && uv run pytest`** (all
  green) in APPROVE comment. Missing this → automatic escalate.
- Phase 3.2 — OpusArchitectReviewer: adversarial review. Focus on the
  backfill idempotency and the `group_id` implicit-filter invariant.
- Phase 4.1 — QAEngineer: live smoke on iMac — see acceptance
  criteria above. Evidence comment with commit SHA + curl/MCP output
  + `MATCH (n:Issue) RETURN DISTINCT n.group_id` count.
- Phase 4.2 — merge to develop after all gates green.

## 9. Risks

- **R1 — iMac production data stamped wrong.** Mitigation: default
  `group_id` matches intent (`project/gimle`), backfill is WHERE-
  guarded so re-running doesn't overwrite.
- **R2 — Wire contract drift.** Mitigation: explicit byte-identical
  check in acceptance criteria; lookup response schema not extended.
- **R3 — Index not applied before first lookup.** Mitigation:
  `ensure_schema()` runs in FastAPI lifespan before any request.
- **R4 — GC accidentally wipes other projects.** Mitigation: the
  `n.group_id = $group_id` filter in `GC_BY_LABEL`. Explicit test
  fixture: create nodes in two projects, run GC for one, assert the
  other is untouched.

## 10. Why this instead of N+1a redesign

N+1a targeted zero raw Cypher, bi-temporal edges, and unlock for
N+1b/c. After revert + API reality check:

- `graphiti-core 0.4.3` cannot hold our domain attributes
  (`status`, `title`, `description`, `body`, `palace_last_seen_at`)
  natively. A full swap is blocked until the library gains custom
  per-node properties, or until we commit to a hybrid that still
  leaves ~60% of persistence as raw Cypher.
- Bi-temporal `ASSIGNED_TO` is a nice-to-have that has not once
  caused a production issue in 16 h of N+0 operation.
- The one concrete unlock we do need — multi-project namespacing —
  costs a single schema column + index, not a substrate rewrite.

When search becomes a driving product need (currently forecast for
N+1c), we will re-evaluate graphiti-core or an alternative (e.g.
Neo4j vector index, Qdrant, …) with a proper spike against the real
API first — see `reference_graphiti_core_api_truth.md`.
