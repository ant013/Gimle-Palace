# M3.A.0 — Per-Tool Bundle-Semantics Design Note

**Issue:** GIM-383
**Author:** CTO (Claude)
**Date:** 2026-05-20
**Status:** Awaiting CR + operator approval
**Spec ref:** `docs/superpowers/specs/2026-05-19-uw-discovery-readiness-roadmap-rev2.md` §M3.A.0

## Scope

Defines bundle behavior for the 6 project-only `palace.code.*` tools that
will receive `bundle=` parameter in M3.A.1–6. Each tool currently accepts
only `project: str`. After M3.A, each will accept mutually exclusive
`project` / `bundle` params (Approach A, operator decision #1).

## Shared conventions

All 6 tools follow the same structural pattern, using
`code_composite.py._resolve_slug()` as the canonical bundle resolver:

1. **Mutual exclusion:** `project` XOR `bundle` required. Both → error
   `mutually_exclusive_args`. Neither → error `missing_target`.
2. **Bundle resolution:** via `_resolve_slug()` in `code_composite.py`,
   which uses the canonical `:CONTAINS` edge:
   `MATCH (b:Bundle {name})-[:CONTAINS]->(p:Project)`.
   Zero members → error `bundle_has_no_members`.
   **Note:** `find_version_skew` uses `:HAS_MEMBER` — this is a legacy
   inconsistency (GIM-218 predates the canonical DDL). The 6 new tools
   MUST use `:CONTAINS` per `memory/bundle.py` and `memory/cypher.py`.
3. **Invalid member slugs:** excluded with warning (not silent drop), per
   `find_version_skew` W11 precedent.
4. **Response envelope:** bundle-mode responses include `"mode": "bundle"`,
   `"target_slug": "<bundle>"`, and a `"bundle_health"` summary from
   `palace.memory.bundle_status()`.
5. **Limit semantics:** `top_n` / `limit` caps apply to the merged result
   set (post-aggregation), not per-member. Per-tool detail below.

### `project_id` format split

The 6 tools use two different node-property conventions for project scoping.
Implementers must use the correct format per tool:

| Property format | Tools | Bundle Cypher variable |
|---|---|---|
| `project_id = "project/<slug>"` | `find_hotspots`, `list_functions`, `find_owners` | `$project_ids` — built as `[f"project/{s}" for s in member_slugs]` |
| `project = "<slug>"` (bare) | `find_dead_symbols`, `find_public_api`, `find_cross_module_contracts` | `$projects` — bare `member_slugs` list |

This split reflects the extractor that writes each node type. Do not
normalize — the bundle layer adapts to the existing property format.

## Tool-by-tool design

---

### 1. `find_hotspots` (M3.A.1)

**Current:** returns top-N files by `hotspot_score` for a single project,
filtered by `project_id = "project/<slug>"`.

**Bundle behavior — global top-N across members:**

The `top_n` parameter applies globally to the merged result set across all
bundle members. Rationale: the operator question is "what are the riskiest
files in the entire bundle?" not "what are each Kit's local hotspots?"
Per-Kit quota would bury high-severity hotspots in large Kits behind
low-severity ones in small Kits.

Implementation: single Cypher query using `IN $project_ids` predicate over
all member `project_id` values, sorted by `hotspot_score DESC`, limited to
`top_n`.

```cypher
MATCH (f:File)
WHERE f.project_id IN $project_ids
  AND coalesce(f.hotspot_score, 0.0) >= $min_score
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN f.project_id AS project_id,
       f.path AS path,
       f.ccn_total AS ccn_total,
       f.churn_count AS churn_count,
       f.hotspot_score AS hotspot_score,
       f.last_complexity_run_at AS computed_at,
       f.complexity_window_days AS window_days
ORDER BY f.hotspot_score DESC
LIMIT $top_n
```

**Response additions:** each row includes `project_id` (stripped to slug)
so the caller knows which member the file belongs to. The
`path_prefix` optional param filters `f.path STARTS WITH $path_prefix`
(per the spec's `find_hotspots(bundle="uw-ios", path_prefix="Modules/Send")`
example).

**v1 simplification:** no per-Kit normalization. If a Kit has stale
hotspot data (extractor not run), its files simply won't appear (they have
`complexity_status = 'stale'` or null). The `bundle_health` section
surfaces which members lack hotspot data.

---

### 2. `list_functions` (M3.A.2)

**Current:** returns functions for a given `(project, path)` pair.

**Bundle behavior — member-resolved path lookup:**

`list_functions` requires an exact `path` parameter. In bundle mode, the
path may exist in exactly one member (Kit-internal files) or rarely in
multiple members (unlikely given distinct repo roots).

Implementation: same `IN $project_ids` Cypher predicate. The query
naturally returns functions from whichever member(s) contain a `:File`
matching that path. Each result row includes the member's `project_id`
(stripped to slug).

```cypher
MATCH (f:File)-[:CONTAINS]->(fn:Function)
WHERE f.project_id IN $project_ids
  AND f.path = $path
  AND fn.ccn >= $min_ccn
RETURN f.project_id AS project_id,
       fn.name AS name,
       fn.start_line AS start_line,
       fn.end_line AS end_line,
       fn.ccn AS ccn,
       fn.parameter_count AS parameter_count,
       fn.nloc AS nloc,
       fn.language AS language
ORDER BY fn.ccn DESC, fn.start_line ASC
```

No `LIMIT` clause in current project-mode; bundle mode maintains the same
(no limit). If no member contains the path, return `ok: true` with empty
result + a diagnostic `"warning": "path_not_found_in_any_member"`.

---

### 3. `find_owners` (M3.A.3)

**Current:** returns top-N owners for `(file_path, project)`. Uses
`OwnershipFileState` and `OwnershipCheckpoint` per-project.

**Bundle behavior — member-resolved file lookup:**

Like `list_functions`, `find_owners` requires a specific `file_path`. In
bundle mode, the file resides in exactly one member project (each Kit has
its own repo mount with distinct paths).

Implementation: fan-out Cypher using `IN $project_ids` on the
`:File.project_id` predicate. The `:OWNED_BY` edges and
`:OwnershipFileState` are per-project, so the query naturally scopes to the
correct member.

**Checkpoint validation change for bundle mode:** in project mode,
`find_owners` checks for an `:OwnershipCheckpoint` before querying and
returns `ownership_not_indexed_yet` if missing. In bundle mode, the
checkpoint check must be **deferred to after the file is located** — first
find which member contains the file via the `:File` query, then check the
checkpoint for that specific member. Do NOT require all 41 members to have
checkpoints; only the member that owns the file matters. If the file is
found but its member lacks a checkpoint, return `ownership_not_indexed_yet`
with `member_project` identifying which member needs the extractor run.

```cypher
MATCH (f:File {path: $path})
WHERE f.project_id IN $project_ids
OPTIONAL MATCH (cp:OwnershipCheckpoint {project_id: f.project_id})
OPTIONAL MATCH (st:OwnershipFileState {path: $path, project_id: f.project_id})
OPTIONAL MATCH (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
WITH f, cp, st, r, a
ORDER BY r.weight DESC
WITH f, cp, st, collect({r: r, a: a}) AS pairs
RETURN f.project_id AS project_id,
       cp IS NOT NULL AS has_checkpoint,
       cp.last_head_sha AS head_sha,
       cp.last_completed_at AS completed_at,
       st.status AS status,
       st.no_owners_reason AS reason,
       st.last_run_id AS last_run_id,
       pairs
```

**Merge rule:** ownership weights are per-project (blame + churn within
that repo). No cross-project ownership merging — the file lives in one
member and its ownership data is self-contained. If the file matches
multiple members (theoretically possible but practically never for UW
bundles), return results grouped by member slug.

**Response additions:** includes `member_project` slug identifying which
member the file was found in. Ownership checkpoint metadata
(`head_sha`, `alpha_used`, etc.) is per-member.

---

### 4. `find_dead_symbols` (M3.A.4)

**Current:** returns `DeadSymbolCandidate` nodes for a project.

**Bundle behavior — v1: per-project union with cross-Kit annotation:**

This tool has the highest cross-Kit reachability complexity (noted in spec
as open question #4). A symbol marked dead in Kit A may be imported and
used by Kit B or the main app — meaning it is NOT dead in the bundle
context even though it appears dead in its own project.

**True cross-Kit reachability analysis** requires resolving import graphs
across projects (Kit A's public API → Kit B's `import` statements). This
depends on:
- `find_public_api` data for each Kit (which symbols are exported)
- `find_references` cross-project search (which exported symbols are used)

This is not feasible in a single M3.A.4 slice without building a new
cross-project reachability resolver.

**v1 design (per-project union):** single Cypher with `IN $projects`
predicate, collecting `DeadSymbolCandidate` from all bundle members. Each
row is tagged with `member_project`. The `limit` applies to the merged set.

```cypher
MATCH (c:DeadSymbolCandidate)
WHERE c.project IN $projects
RETURN c.project AS member_project,
       c.id AS id,
       c.display_name AS display_name,
       c.kind AS kind,
       c.module_name AS module_name,
       c.language AS language,
       c.candidate_state AS candidate_state,
       c.confidence AS confidence,
       c.source_file AS source_file,
       c.source_line AS source_line,
       c.commit_sha AS commit_sha,
       c.evidence_source AS evidence_source
ORDER BY c.project, c.module_name, c.display_name
LIMIT $limit
```

This is equivalent to "what does each project think is dead,
shown together." The response includes a caveat field:

```json
{
  "ok": true,
  "mode": "bundle",
  "target_slug": "uw-ios",
  "caveat": "v1_per_project_union",
  "caveat_detail": "Candidates are per-project dead-symbol analysis. A symbol dead in one Kit may be consumed by another Kit — cross-Kit reachability filtering is a v2 follow-up.",
  "result": [...]
}
```

**v2 follow-up (post-M3):** cross-Kit reachability filter that checks each
dead candidate's FQN against `find_references(bundle=...)` — if a bundle-
wide reference exists, demote from "dead" to "Kit-internal-only-dead"
(informational). Filed as a separate issue after M3 lands.

**Escalation per spec open question #4:** v1 ships per-project union. If
operator requires true cross-Kit analysis before M3 gate, this slice
escalates to Board.

---

### 5. `find_public_api` (M3.A.5)

**Current:** returns `PublicApiSurface → PublicApiSymbol` for a project.

**Bundle behavior — all members (app + Kits):**

Scope decision: **include all members** (app + all Kits). Rationale: an
agent discovering "what public API surface does this bundle expose?" needs
the full picture — Kit APIs are the primary reuse surface (Kits export
protocols, services, and view models consumed by the app and other Kits).
Showing only app-level API would miss the most useful discovery data.

Implementation: `IN $project_ids` predicate on both
`PublicApiSurface.project` and `PublicApiSymbol.project`.

```cypher
MATCH (surface:PublicApiSurface)-[:EXPORTS]->(sym:PublicApiSymbol)
WHERE surface.project IN $projects
  AND sym.project IN $projects
RETURN surface.module_name AS module_name,
       sym.project AS member_project,
       sym.fqn AS fqn,
       sym.display_name AS display_name,
       sym.kind AS kind,
       sym.visibility AS visibility,
       sym.commit_sha AS commit_sha,
       sym.signature AS signature,
       sym.language AS language
ORDER BY sym.project, surface.module_name, sym.fqn
LIMIT $limit
```

**Response additions:** each row includes `member_project` to identify
which Kit/app the symbol belongs to. Results are ordered by member first,
then module, then FQN — giving a grouped view.

---

### 6. `find_cross_module_contracts` (M3.A.6)

**Current:** returns `ModuleContractDelta` for a project (consumer ↔
producer module contract drift).

**Bundle behavior — intra-bundle contract visibility:**

In project mode, contract deltas capture drift between modules within one
repo. In bundle mode, the interesting new dimension is **cross-Kit contract
drift**: Kit A consumes symbols from Kit B's public API; Kit B changes that
API; the delta shows up as a `ModuleContractDelta`.

**v1 design (per-project union):** collect `ModuleContractDelta` from all
bundle members using `IN $projects` predicate. This captures intra-module
contracts within each Kit/app. Cross-Kit contracts (Kit A → Kit B) would
require a new extractor that compares import statements against public API
changes across repos — this is out of scope for M3.A.6.

```cypher
MATCH (d:ModuleContractDelta)
WHERE d.project IN $projects
RETURN d.project AS member_project,
       d.consumer_module_name AS consumer_module,
       d.producer_module_name AS producer_module,
       d.language AS language,
       d.from_commit_sha AS from_commit,
       d.to_commit_sha AS to_commit,
       d.removed_consumed_symbol_count AS removed_count,
       d.added_consumed_symbol_count AS added_count,
       d.signature_changed_consumed_symbol_count AS signature_changed_count,
       d.affected_use_count AS affected_use_count
ORDER BY d.to_commit_sha DESC, d.project, d.consumer_module_name
LIMIT $limit
```

**Response additions:** `member_project` per row. Sorted by recency then
member then consumer module.

**v2 follow-up:** cross-Kit contract delta extractor that joins Kit A's
imports with Kit B's `find_public_api` change history. Separate issue.

---

## Summary table

| Tool | Bundle merge strategy | Cypher variable | `top_n`/`limit` scope | Key design choice | v2 follow-up? |
|---|---|---|---|---|---|
| `find_hotspots` | Single Cypher `IN` | `$project_ids` (`"project/…"`) | Global post-merge | Global ranking, no per-Kit quota | No |
| `list_functions` | Single Cypher `IN` | `$project_ids` (`"project/…"`) | No limit (same as project) | Path resolves to whichever member has it | No |
| `find_owners` | Single Cypher `IN` | `$project_ids` (`"project/…"`) | `top_n` per-file (one member) | Checkpoint check deferred to post-file-match | No |
| `find_dead_symbols` | Single Cypher `IN` | `$projects` (bare slug) | Global `limit` post-merge | v1 union only; no cross-Kit reachability | **Yes** |
| `find_public_api` | Single Cypher `IN` | `$projects` (bare slug) | Global `limit` post-merge | All members (app + Kits), not app-only | No |
| `find_cross_module_contracts` | Single Cypher `IN` | `$projects` (bare slug) | Global `limit` post-merge | v1 intra-project contracts only | **Yes** |

## Implementation pattern reference

**Canonical resolver:** `code_composite.py._resolve_slug()` — uses
`:CONTAINS` edge (correct). Do NOT copy `find_version_skew`'s
`_bundle_members()` which uses the legacy `:HAS_MEMBER` edge type.

All 6 tools should follow this structural pattern:

1. Validate `project` XOR `bundle` mutual exclusion
2. Resolve bundle → member slugs via `_resolve_slug()` or equivalent
   Cypher: `MATCH (b:Bundle {name: $slug})-[:CONTAINS]->(p:Project)`
3. Build the appropriate variable per the `project_id` format split table:
   - `project_ids = [f"project/{s}" for s in member_slugs]` for tools
     using `project_id` property (`find_hotspots`, `list_functions`,
     `find_owners`)
   - `projects = member_slugs` for tools using bare `project` property
     (`find_dead_symbols`, `find_public_api`,
     `find_cross_module_contracts`)
4. Execute single Cypher with `IN` predicate
5. Return with `mode`, `target_slug`, `bundle_health`, per-row
   `member_project`

Single-Cypher `IN` is preferred over per-member fan-out because:
- All backing data is in Neo4j (no Tantivy search needed unlike
  `find_references`)
- Single query is simpler and avoids N+1 round-trips for 41-member bundles
- Neo4j handles `IN` predicates efficiently on indexed properties

## Acceptance criteria

- [x] This document committed at `docs/runbooks/m3-bundle-semantics-design.md`
- [ ] CR Phase 1.2 review passed
- [ ] Operator explicitly approves before M3.A.1 starts
