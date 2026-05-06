---
title: Cross-repo version skew extractor — pure skew detection over GIM-191 :DEPENDS_ON
slug: cross-repo-version-skew
date: 2026-05-06
status: proposed
paperclip_issue: GIM-NN
predecessor_sha: 0a9c2363a
authoring: Board+Claude
team: Claude
roadmap_item: "#39 Cross-Repo Version Skew"
roadmap_source: "docs/roadmap.md §2.1 Structural, row #39 (verified 2026-05-06 by Board+Claude after GIM-191 dependency_surface merged 2026-05-04)"
---

# Cross-repo version skew extractor (Roadmap #39)

## 1. Context

Roadmap §2.1 row #39 — Cross-Repo Version Skew. Unblocked the moment
GIM-191 `dependency_surface` merged (`9038d7f`, 2026-05-04) which
populated `:Project-[:DEPENDS_ON]->:ExternalDependency` graph for the
SPM / Gradle / Python ecosystems. This slice does **not** add new
extraction; it composes a query on top of GIM-191 data and exposes
one MCP tool.

**Product question this slice answers**: «Where do my projects /
modules / bundle members disagree on the resolved version of the same
external library?» — for the UW iOS bundle (41 first-party HS Kits +
UW iOS app) the canonical pain is silent binary-incompatibility
between Kits pinning different versions of shared libs (BigInt,
swift-numerics, web3.swift). For UW Android (multi-module monorepo)
the same pain occurs across `app/build.gradle.kts`,
`core:build.gradle.kts` etc.

**Source-of-truth artefacts already on develop@`0a9c2363a`:**

- `:ExternalDependency {purl}` — `extractors/dependency_surface/neo4j_writer.py:_MERGE_DEP_CYPHER`
- `(:Project)-[:DEPENDS_ON {scope, declared_in, declared_version_constraint}]->(:ExternalDependency)` — same writer
- purl format includes version after `@`:
  - `pkg:github/horizontalsystems/marketkit@1.5.0`
  - `pkg:maven/com.example/lib@1.0.0`
  - `pkg:pypi/requests@2.31.0`
- `:Bundle{name}` + `:HAS_MEMBER` from GIM-182 multi-repo SPM ingest
- `palace.memory.bundle_members(name)` — substrate helper
- Foundation: `BaseExtractor`, `create_ingest_run`, `finalize_ingest_run`,
  `ExtractorErrorCode`, Pydantic v2 frozen models

**Operator-facing query this slice ships:**

`palace.code.find_version_skew(project|bundle, ecosystem?, min_severity?, top_n=50, include_aligned=False)` →
ranked skew groups
`(purl_root, ecosystem, severity, version_count, entries[{scope_id, version, declared_in, declared_constraint}])`
with provenance metadata
`(mode, target_slug, total_skew_groups, summary_by_severity, last_run_at, last_run_id)`.

## 2. Scope

### IN (v1)

- New extractor `cross_repo_version_skew` registered in `EXTRACTORS`.
- New MCP tool `palace.code.find_version_skew` registered next to
  `find_references` / `find_hotspots` / `find_owners`.
- Pure read aggregation over existing
  `(:Project)-[:DEPENDS_ON]->(:ExternalDependency)` edges.
- Two modes via mutually-exclusive args: `project=<slug>`
  (intra-module skew via `r.declared_in`) OR `bundle=<name>`
  (cross-member skew via `palace.memory.bundle_members`).
- `resolved_version` comparison only (parsed from `purl@version`);
  `declared_version_constraint` carried for display.
- Best-effort semver classification via `packaging.version` →
  `severity ∈ {patch, minor, major, unknown}`. Non-parseable
  versions classify as `unknown`.
- Filters: `ecosystem`, `min_severity`, `top_n`, `include_aligned`.
- Substrate-aligned `:IngestRun{source='extractor.cross_repo_version_skew'}`
  with ownership-style extras (mode, target_slug, summary counts).
- No new Neo4j nodes / edges / constraints / indexes.
- Update `CLAUDE.md ## Extractors` with operator workflow.

### OUT (v1, explicitly deferred)

- F1. **Precomputed `:VersionSkew` nodes** — would let cached queries
  read the latest skew snapshot without recomputing. Cypher
  aggregation is fast enough at UW scale (200 ms warm on 41-member
  bundle); deferred until perf actually matters.
- F2. **"Latest version" feed (Renovate / GitHub Releases / deps.dev)**
  — answers «is X@1.5.0 obsolete?». Different external API surface
  per ecosystem; would need its own ingest cadence + auth. Roadmap
  mentions Renovate; v1 ships without.
- F3. **CVE enrichment (NVD / OWASP Dep-Check)** — answers «does
  X@1.5.0 have known CVEs?». OWASP Dep-Check is a 3+ GiB JVM tool
  not deployable in palace-mcp container. NVD direct API is
  rate-limited. Followup as own slice.
- F4. **`declared_version_constraint` skew** — when modules express
  different version ranges (`^1.5.0` vs `^1.6.0`) but resolve to the
  same version, that's a constraint-level disagreement we don't
  flag in v1. `resolved_version` is the binary-incompatibility
  signal; declared-constraint analysis is for upgrade planning.
- F5. **Auto-classification of severity beyond semver** — calendar
  versions, git-shas, custom schemes are `unknown` in v1. A
  per-ecosystem heuristic (`packaging`-PEP440 for pypi; semver-strict
  for github SPM; Maven `release/snapshot` aware) is followup.
- F6. **Drift detection between runs** — already achievable via
  `palace.memory.lookup(filters={source='extractor.cross_repo_version_skew',
  target_slug='uw-ios'})` returning `skew_groups_total` per `:IngestRun`.
  No persistent diff state needed in v1.
- F7. **Cross-bundle skew** — comparing `uw-ios` and `uw-android`
  bundles. Different ecosystems (github vs maven), apples-to-oranges.
  No use case yet.
- F8. **Symbol-level skew** — «which symbol from
  `pkg:github/x/y@1.5.0` is no longer present in `@2.0.0`». Requires
  cross-version symbol_index walks; followup if breakage from
  binary-skew bites.

## 3. Decisions and trade-offs (rationale captured during brainstorm)

- **R1 (scope) — pure skew detection from existing graph; no Renovate/OWASP.**
  Roadmap row §2.1 #39 names "Gradle Tooling API + Renovate data +
  OWASP Dep-Check" as the maximal tool stack. v1 takes the bottom
  layer — pure aggregation over what GIM-191 already wrote — and
  defers the external-feed layers (F2, F3) to their own slices.
  Symmetric with #32/#44 narrow-v1 pattern.

- **R2 (architecture) — Hybrid: minimal extractor + live MCP tool.**
  Pure-MCP-tool was an option (one Cypher wrapper, no extractor),
  but breaks the operator-intuitive pattern «every roadmap row is
  an extractor». Precomputed `:VersionSkew` nodes was an option
  (cached snapshot), but adds schema for a query that runs in
  ms-to-200ms range at UW scale. The hybrid: extractor that writes
  ONE `:IngestRun` per call with summary stats (audit + drift
  observability), MCP tool that runs live aggregation Cypher.
  Single source of truth for the aggregation logic
  (`_compute_skew_groups()` shared between extractor Phase 3 and
  MCP tool).

- **R3 (mode coverage) — both project (intra-module) AND bundle (cross-member).**
  UW iOS bundle = 41 separate `:Project` nodes; without bundle-mode
  the primary product target (cross-Kit drift) is invisible. UW
  Android = 1 `:Project` with multi-module `r.declared_in` paths;
  without project-mode (intra-module) the multi-module monorepo case
  is invisible. Two modes via mutually-exclusive `project=` /
  `bundle=` args; identical response shape; `scope_id` source
  differs (`r.declared_in` vs `member.slug`).

- **R4 (granularity) — `resolved_version` only; `declared_constraint`
  carried for display.** Resolved versions are the actual binary-
  incompatibility risk (lockfile says «MarketKit got BigInt@1.5.0,
  EvmKit got BigInt@1.6.1»). Constraint-level skew (`^1.5.0` vs
  `^1.6.0`) is upgrade-planning signal; less critical, deferred F4.

- **R5 (severity classification) — Hybrid semver, fallback `unknown`.**
  UW Swift / Gradle / Python deps are semver-ish in 90%+ of cases.
  `packaging.version.parse` (PEP 440) is lenient enough for the
  union. Calendar versions / git-shas / custom schemes degrade to
  `unknown`; still surface in default response. `min_severity`
  filter explicit ranking: `patch < minor < major; unknown` is a
  separate category, returned only when explicitly included.

- **R6 (defaults) — narrow happy path.** Min cohort size = 2,
  single-source deps excluded, aligned-versions excluded by default
  (opt-in via `include_aligned=False`). top_n=50, range [1, 500].
  Default `min_severity=None` returns all severities (incl.
  `unknown`); operator filters as needed.

## 4. Architecture

### File layout

```
services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/
├── __init__.py
├── extractor.py               # CrossRepoVersionSkewExtractor(BaseExtractor)
├── models.py                  # SkewGroup, SkewEntry, SkewSummary, RunSummary
├── purl_parser.py             # split_purl(purl) → (root, version, ecosystem)
├── semver_classify.py         # classify(v_a, v_b) → 'patch'|'minor'|'major'|'unknown'
├── compute.py                 # _compute_skew_groups(driver, members, ecosystem)
└── neo4j_writer.py            # _write_run_extras() for :IngestRun summary

services/palace-mcp/src/palace_mcp/code/
└── find_version_skew.py       # MCP tool wrapper (typed envelope, error codes)
```

### Phase pipeline (extractor)

```
Phase 0 — bootstrap
  • check_resume_budget(prev_error_code)        ← substrate
  • create_ingest_run(driver, run_id, project, extractor_name='cross_repo_version_skew')
  • resolve_targets(ctx):
      if ctx has 'bundle': members = bundle_members(driver, bundle)
      else:                members = [ctx.project]

Phase 1 — verify dependency_surface indexed
  • for member in members:
      MATCH (p:Project {slug: $member})-[:DEPENDS_ON]->(:ExternalDependency)
      RETURN count(*) AS n
  • build target_status: dict[member, 'indexed' | 'not_indexed']
  • if all not_indexed → fail dependency_surface_not_indexed
  • if some not_indexed → continue with warnings

Phase 2 — aggregate skew (one Cypher; mode-conditional scope_id)
  • execute aggregation Cypher (see §5 Cypher fragments)
  • returns rows of {purl_root, ecosystem, scope_id, version,
                     declared_constraint, declared_in}

Phase 3 — group + classify (shared compute, pure Python)
  • group rows by (purl_root, ecosystem)
  • for each group:
      distinct_versions = sorted(set(row.version for row in group))
      if len(distinct_versions) < 2: continue   # not skew (rule 6a/6b)
      severity = max-pairwise-classify(distinct_versions)
        — semver_classify.classify(v_a, v_b) on every pair
        — final = highest-rank seen ('major' > 'minor' > 'patch' > 'unknown')
      emit SkewGroup(purl_root, ecosystem, severity, entries=[...])

Phase 4 — summary stats + finalize
  • compute counts per severity, count of aligned groups
  • _write_run_extras(driver, run_id, mode, target_slug,
                      member_count, target_status,
                      skew_groups_total, skew_groups_by_severity,
                      aligned_groups_total)
  • finalize_ingest_run(driver, run_id, success=True)
  • return ExtractorStats(nodes_written=1 [:IngestRun],
                          edges_written=0,
                          summary=skew_groups_total)
```

### MCP tool surface (`palace.code.find_version_skew`)

**Args:**

| Name | Type | Default | Constraint |
|------|------|---------|------------|
| `project` | str \| None | None | mutually-exclusive with `bundle` |
| `bundle` | str \| None | None | mutually-exclusive with `project` |
| `ecosystem` | str \| None | None | one of `'github' \| 'maven' \| 'pypi' \| None` |
| `min_severity` | str \| None | None | one of `'patch' \| 'minor' \| 'major' \| 'unknown' \| None` |
| `top_n` | int | 50 | `1 ≤ top_n ≤ 500` |
| `include_aligned` | bool | False | when True, return purl_roots with `version_count == 1` too |

**Success envelope:**

```python
{
    "ok": True,
    "mode": "project" | "bundle",
    "target_slug": "uw-android" | "uw-ios",
    "skew_groups": [
        {
            "purl_root": "pkg:github/horizontalsystems/marketkit",
            "ecosystem": "github",
            "severity": "major",
            "version_count": 2,
            "entries": [
                {"scope_id": "uw-ios-app", "version": "1.5.0",
                 "declared_in": "Package.swift",
                 "declared_constraint": "^1.5.0"},
                {"scope_id": "MarketKit",   "version": "2.0.1",
                 "declared_in": "Package.swift",
                 "declared_constraint": "^2.0.0"},
            ],
        },
    ],
    "total_skew_groups": 17,                    # before top_n / min_severity filtering
    "summary_by_severity": {"major": 3, "minor": 8, "patch": 4, "unknown": 2},
    "aligned_groups_total": 42,                 # only present when include_aligned=False
    "target_status": {"uw-ios-app": "indexed", "MarketKit": "indexed"},
    "warnings": [],                             # populated when partial coverage
    "last_run_at": "2026-05-06T...",
    "last_run_id": "uuid-...",
}
```

**Sort order**: `(severity desc, version_count desc, purl_root asc)`. Total
order — no ties for unstable order.

### Component responsibilities

| Module | What | Depends on |
|--------|------|-------|
| `purl_parser.py` | `split_purl("pkg:github/h/mk@1.5.0")` → `("pkg:github/h/mk", "1.5.0", "github")`. Pure string. | nothing |
| `semver_classify.py` | `classify("1.5.0", "1.6.1")` → `"minor"`; non-parseable → `"unknown"`. Uses `packaging.version`. | `packaging` (already pinned via existing transitive deps) |
| `compute.py` (`_compute_skew_groups`) | Shared aggregation: Cypher → group → classify → SkewGroup list. Used by extractor Phase 3 AND MCP tool. | purl_parser, semver_classify |
| `extractor.py` | 4-phase orchestrator. | foundation, compute, neo4j_writer |
| `neo4j_writer.py` | `_write_run_extras(driver, run_id, ...)` — single Cypher updates `:IngestRun`. | Neo4j driver |
| `find_version_skew.py` (MCP) | Validates args, resolves targets via bundle_members, calls `_compute_skew_groups()`, applies post-filters (min_severity, ecosystem, top_n, include_aligned), serializes. | compute, palace.memory.bundle_members |

**Key boundary:** `compute.py:_compute_skew_groups()` is single source of truth. Same code path for extractor Phase 3 and MCP live tool — guarantees the `:IngestRun` summary stats reflect what the tool would return.

## 5. Schema

### New nodes / edges

**None.**

### `:IngestRun` extension properties

Substrate fields (from `foundation/checkpoint.py:create_ingest_run` /
`finalize_ingest_run`): `run_id` (UUID, PK), `project`, `source`,
`started_at`, `completed_at`, `success`, `error_code`, `duration_ms`.

Ownership-style extras set by this extractor only:

| Property | Type | Note |
|----------|------|------|
| `mode` | string | `'project' \| 'bundle'` |
| `target_slug` | string | for `mode='project'` — slug; for `'bundle'` — bundle name |
| `member_count` | int | members iterated (1 for project mode) |
| `target_status_indexed_count` | int | how many members had `:DEPENDS_ON` data |
| `skew_groups_total` | int | before filter / top_n |
| `skew_groups_major` | int | |
| `skew_groups_minor` | int | |
| `skew_groups_patch` | int | |
| `skew_groups_unknown` | int | |
| `aligned_groups_total` | int | purl_roots with `version_count == 1` (observability) |

### Aggregation Cypher

**Project-mode** (intra-module via `r.declared_in`):

```cypher
MATCH (p:Project {slug: $slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WITH p, r, d,
     split(d.purl, '@')[0] AS purl_root,
     CASE WHEN size(split(d.purl, '@')) >= 2
          THEN split(d.purl, '@')[1] ELSE NULL END AS resolved_version,
     CASE WHEN size(split(split(d.purl, ':')[1], '/')) >= 1
          THEN split(split(d.purl, ':')[1], '/')[0] ELSE 'unknown' END AS ecosystem
WHERE ($ecosystem IS NULL OR ecosystem = $ecosystem)
  AND resolved_version IS NOT NULL
RETURN purl_root,
       ecosystem,
       r.declared_in AS scope_id,
       resolved_version AS version,
       r.declared_version_constraint AS declared_constraint,
       r.declared_in AS declared_in
ORDER BY purl_root, scope_id
```

**Bundle-mode** (cross-member via `:Bundle{name}`-resolved members):

```cypher
UNWIND $member_slugs AS slug
MATCH (p:Project {slug: slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WITH p, r, d,
     split(d.purl, '@')[0] AS purl_root,
     CASE WHEN size(split(d.purl, '@')) >= 2
          THEN split(d.purl, '@')[1] ELSE NULL END AS resolved_version,
     CASE WHEN size(split(split(d.purl, ':')[1], '/')) >= 1
          THEN split(split(d.purl, ':')[1], '/')[0] ELSE 'unknown' END AS ecosystem
WHERE ($ecosystem IS NULL OR ecosystem = $ecosystem)
  AND resolved_version IS NOT NULL
RETURN purl_root,
       ecosystem,
       p.slug AS scope_id,
       resolved_version AS version,
       r.declared_version_constraint AS declared_constraint,
       r.declared_in AS declared_in
ORDER BY purl_root, scope_id
```

The two queries differ only in the `MATCH` (single project vs UNWIND) and `scope_id` source (`r.declared_in` vs `p.slug`); the rest is shared. `_compute_skew_groups()` selects the right query based on mode.

### Indexes / constraints

None new. Substrate `:IngestRun.run_id` UNIQUE constraint already exists. `:Project{slug}` and `:ExternalDependency{purl}` UNIQUE constraints are owned by GIM-191 / substrate.

## 6. Configuration (env vars)

Added to `PalaceSettings` (`config.py`), prefix `PALACE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PALACE_VERSION_SKEW_TOP_N_MAX` | `500` | Upper bound for `top_n` arg; out of range → `top_n_out_of_range` |

Reused: `PALACE_RECENCY_DECAY_DAYS` is **not** used (no time-decay component). Substrate Tantivy caps (`PALACE_MAX_OCCURRENCES_*`) do **not** apply (no Tantivy writes).

## 7. MCP tool error envelopes

| `error_code` | Trigger | Resolution-order rank |
|--------------|---------|------------------------|
| `top_n_out_of_range` | `top_n ∉ [1, 500]` | 1 (validate before any DB hit) |
| `slug_invalid` | bad slug regex (re-using existing pattern) | 1 |
| `mutually_exclusive_args` | both `project=` and `bundle=` non-null | 1 |
| `missing_target` | both `project=` and `bundle=` null | 1 |
| `invalid_severity_filter` | `min_severity ∉ {None, 'patch', 'minor', 'major', 'unknown'}` | 1 |
| `invalid_ecosystem_filter` | `ecosystem ∉ {None, 'github', 'maven', 'pypi'}` | 1 |
| `project_not_registered` | `(:Project{slug})` does not exist (project-mode) | 2 |
| `bundle_not_registered` | `(:Bundle{name})` does not exist (bundle-mode) | 2 |
| `dependency_surface_not_indexed` | for ALL targets `count((p)-[:DEPENDS_ON]) = 0` | 3 |

`target_status` map is **always** populated in the success envelope (and informational warnings when ≥1 but <all targets are indexed).

## 8. Error handling and idempotency

### `ExtractorErrorCode` additions

Some codes already added for GIM-216 (`ownership_diff_failed`, etc.). New for #39:

| Code | When |
|------|------|
| `dependency_surface_not_indexed` | for all targets `count((p)-[:DEPENDS_ON]) = 0` |
| `bundle_not_registered` | `palace.memory.bundle_members(bundle)` empty |
| `mutually_exclusive_args` | both `project` and `bundle` args set |
| `missing_target` | both `project` and `bundle` null |
| `invalid_severity_filter` | bad `min_severity` value |
| `invalid_ecosystem_filter` | bad `ecosystem` value |

Existing substrate codes used as-is: `project_not_registered`,
`slug_invalid`, `top_n_out_of_range`, `extractor_runtime_error`.

### Idempotency invariants

1. **Pure read on existing graph.** No mutations to `:Project`,
   `:ExternalDependency`, `:DEPENDS_ON`, `:Bundle`, or any pre-existing
   node/edge. Verified by acceptance criterion #14: snapshot graph
   counts before and after extract; delta = exactly one new
   `:IngestRun`.
2. **One `:IngestRun` per `extract()` call.** Two consecutive runs →
   two distinct `:IngestRun` nodes. Both visible via
   `palace.memory.lookup`. Drift detection (F6) is the operator's
   own composition over those snapshots.
3. **MCP tool determinism.** Same inputs + same graph → identical
   response. Sort key
   `(severity_rank desc, version_count desc, purl_root asc)` is a
   total order.
4. **Stale `:IngestRun.skew_groups_total` is design intent**, not
   inconsistency. The MCP tool always recomputes live; the
   `:IngestRun` snapshot exists only for between-runs observability.

### Edge cases

| Case | Behavior |
|------|----------|
| Project has 0 `:DEPENDS_ON` (new repo, dependency_surface not yet run) | Project mode: `dependency_surface_not_indexed`. Bundle mode: `target_status[slug] = 'not_indexed'`; if ANY member is indexed → success-with-warning; if ALL → fail. |
| Single-source dep (only 1 scope pins it) | `WHERE size(collect(DISTINCT version)) >= 2` on group → not in skew_groups output. Counted in `aligned_groups_total`. |
| `:ExternalDependency.purl` without `@version` | Cypher filter `resolved_version IS NOT NULL`; group excluded; warning `purl_missing_version: <count>` added to `:IngestRun.warnings`. |
| One scope_id with multiple versions of same lib (nonsense) | Group keeps both entries; tool surfaces them as separate rows under one `scope_id`. Not failure. |
| Bundle with stale member (slug listed in `:HAS_MEMBER` but no `:Project{slug}`) | `MATCH (p:Project{slug: stale_slug})` returns empty; `target_status[stale_slug] = 'not_registered'`; `member_count` only counts registered members. |
| `purl_parser` on exotic prefix (`pkg:cocoapods/...`) | Extract as-is, ecosystem = `'cocoapods'`. Filter `ecosystem='github'` excludes. Not failure. |
| Versions `"1.5.0"` and `"1.5"` (parse-equivalent under `packaging.version`) | **Reported as skew** because grouping uses raw-string distinctness (`set(row.version for row in group)` keeps both). Severity is whatever pairwise-classify says — for `"1.5"` vs `"1.5.0"` `packaging` yields equal Version objects → `classify()` returns `patch` (defined as: parse OK and major+minor equal → `patch`; major+minor+micro all equal returns `patch` too because we don't distinguish "exactly equal" from "patch-different"). **Tradeoff documented**: prefer raw-string distinctness over post-parse equivalence so we surface "the manifest text is divergent" even when binary is equivalent. Operator can hide such noise via `min_severity='minor'`. |

### PII discipline

This extractor does NOT touch `:Author` or any email-bearing nodes.
No PII surface. `error_message` and INFO logs reference paths,
SHAs, and slugs only — same hard rule as GIM-216 §8 carries.

## 9. Acceptance criteria

A successful run + tool query produces, given a project / bundle with
`dependency_surface` already indexed:

1. **Extractor bootstrap completes for project-mode.** Run with
   `ctx.project='uw-android'`; `:IngestRun{source='extractor.cross_repo_version_skew',
   mode='project', target_slug='uw-android', success=true}` written;
   `skew_groups_*` counts match what `find_version_skew(project='uw-android')`
   returns synchronously after.
2. **Extractor bootstrap completes for bundle-mode.** Run with
   `ctx.bundle='uw-ios'`; `:IngestRun{mode='bundle',
   target_slug='uw-ios', member_count > 1, success=true}` written.
3. **No-op semantics on a target with no skew.** Project that has
   only single-source deps → `:IngestRun.skew_groups_total = 0`,
   `:IngestRun.aligned_groups_total > 0`, success.
4. **Project-mode → intra-module skew via `r.declared_in`.** Synthetic
   project `mock-android` with same dep at 2 declared_in paths and
   different versions → `find_version_skew(project='mock-android')`
   returns 1 SkewGroup with 2 entries; `scope_id` = `r.declared_in`.
5. **Bundle-mode → cross-member skew.** Mini-fixture with 4 projects
   in a bundle, 2 of which pin different versions of one purl_root
   → 1 SkewGroup with 2 entries; `scope_id` = member slugs.
6. **`min_severity='major'` filter.** Bundle-mode call returns only
   major-classified groups; minor / patch / unknown are filtered out.
   `total_skew_groups` and `summary_by_severity` reflect pre-filter counts.
7. **`ecosystem='github'` filter.** Only purl_roots with
   `pkg:github/...` returned.
8. **`include_aligned=True`.** purl_roots with `version_count == 1`
   appear in `skew_groups` (with `severity=null`); aligned-and-skew
   groups co-exist.
9. **`top_n=1`.** Returns 1 group, the highest-priority one per
   sort key.
10. **`dependency_surface_not_indexed` error.** Wipe `:DEPENDS_ON`,
    attempt extract → fail-fast with this code (project-mode);
    bundle-mode partial coverage → success with `target_status` map.
11. **Mutually-exclusive args error.** Both `project=` and
    `bundle=` set → `mutually_exclusive_args`.
12. **Missing target error.** Neither set → `missing_target`.
13. **Bundle not registered error.** `bundle='ghost'` not in graph →
    `bundle_not_registered`.
14. **Pure-read invariant.** Snapshot node + edge counts before
    `extract()`. After: delta = exactly one new `:IngestRun`. No
    other node/edge created or mutated.
15. **Single source of truth via `_compute_skew_groups()`.**
    Extractor's Phase 3 result and the MCP tool's response (when
    invoked synchronously after with same args) report identical
    `total_skew_groups` and identical SkewGroup composition. (Test:
    snapshot extractor's run output and tool's response in the same
    fixture state, assert structural equality.)
16. **Sort total order.** Two runs over identical fixture produce
    identical `skew_groups` ordering. Verified by sorting check
    in integration test.
17. **Re-run produces fresh `:IngestRun`.** Two consecutive
    `extract()` calls → two distinct `run_id`s; both queryable via
    `palace.memory.lookup`.

## 10. Test plan

### 10.1 Unit (mock driver, fast)

| File | Scope |
|------|-------|
| `tests/extractors/unit/test_cross_repo_skew_purl_parser.py` | `split_purl()` for all ecosystems (github / maven / pypi / generic-fallback); missing-`@version`; multiple `@`; URL-encoded chars |
| `tests/extractors/unit/test_cross_repo_skew_semver_classify.py` | identical → `patch` (no skew anyway); `1.5.0` vs `1.5.1` → `patch`; `1.5.0` vs `1.6.0` → `minor`; `1.5.0` vs `2.0.0` → `major`; `1.5.0` vs `calver-2024.05.06` → `unknown`; `unknown` floor propagates; max-pairwise across version_list of 3+ |
| `tests/extractors/unit/test_cross_repo_skew_models.py` | Pydantic validators on SkewGroup, SkewEntry, SkewSummary, RunSummary |
| `tests/extractors/unit/test_cross_repo_skew_compute.py` | Mock-driver — `_compute_skew_groups()` from synthetic Cypher rows; verify grouping, ordering, severity computation; verify single-source filter (rule 6b); verify aligned-vs-skew classification with `include_aligned` flag |

### 10.2 Integration (real Neo4j via testcontainers)

`tests/extractors/integration/test_cross_repo_skew_integration.py` against new fixture
`tests/extractors/fixtures/cross-repo-skew-mini-project/` seeded
directly via Cypher (no manifest parsing — we're testing the skew
detection layer, not GIM-191):

- 4 `:Project` nodes (`uw-ios-app`, `MarketKit`, `EvmKit`, `BitcoinKit`)
- 1 `:Bundle{name='uw-ios-mini'}` with all four as members
- ~12 `:ExternalDependency` nodes covering: known major skew, known
  patch skew, single-source dep, aligned dep, unknown-version dep,
  cocoapods (exotic prefix), missing-`@version` (corner)

Scenarios — exact mapping to acceptance criteria:

1. Bootstrap project-mode (acceptance #1)
2. Bootstrap bundle-mode (acceptance #2)
3. No-skew target (acceptance #3)
4. Project-mode intra-module skew (acceptance #4) — synthetic graph injection
5. Bundle-mode cross-member skew (acceptance #5)
6. `min_severity='major'` filter (acceptance #6)
7. `ecosystem='github'` filter (acceptance #7)
8. `include_aligned=True` (acceptance #8)
9. `top_n=1` (acceptance #9)
10. `dependency_surface_not_indexed` (acceptance #10) — wipe :DEPENDS_ON, retry
11. Pure-read invariant (acceptance #14) — snapshot before/after
12. Single source of truth via shared compute (acceptance #15)
13. Sort total order (acceptance #16)
14. Re-run produces fresh :IngestRun (acceptance #17)

### 10.3 Wire-contract (MCP tool)

`tests/code/test_find_version_skew_wire.py`:

- All 9 error codes explicitly tested via `result["error_code"] == "..."` (per
  `feedback_wire_test_tautological_assertions`).
- Success envelope shape for project + bundle modes.
- `top_n=1`, `top_n=50`, `top_n=500` clamp + length checks.

### 10.4 Smoke (live, on iMac)

`tests/extractors/smoke/test_cross_repo_skew_smoke.sh`:

- Run extract on `uw-ios` bundle (41 HS Kits + uw-ios-app), then
  `uw-android` project.
- Assertions: `skew_groups_total > 0` (UW likely has SOME drift);
  `:IngestRun` visible via `palace.memory.lookup`; sub-200ms tool
  response on warm cache (perf SLO check).
- Manual; not in CI.

### 10.5 Coverage matrix

| Component | Unit | Integration | Wire | Smoke |
|-----------|:----:|:-----------:|:----:|:-----:|
| `purl_parser.py` | ✅ | ✅ (via `_compute_skew_groups`) | — | ✅ |
| `semver_classify.py` | ✅ | ✅ | — | ✅ |
| `models.py` | ✅ | — | — | — |
| `compute.py` (`_compute_skew_groups`) | ✅ | ✅ (sc 1, 4, 5, 12) | — | ✅ |
| `extractor.py` orchestrator | — | ✅ (sc 1, 2, 3, 14) | — | ✅ |
| `find_version_skew.py` MCP tool | — | ✅ (sc 6, 7, 8, 9, 10) | ✅ | ✅ |
| `_write_run_extras` | — | ✅ (sc 1, 2, 17) | — | ✅ |

## 11. Operator workflow (CLAUDE.md addition)

```
### Operator workflow: Cross-repo version skew

Prereq: GIM-191 `dependency_surface` extractor must have run for the
target project (or every member of the target bundle).

1. Run the extractor:
   palace.ingest.run_extractor(name="cross_repo_version_skew", project="uw-android")
   # or, for a bundle:
   palace.ingest.run_extractor(name="cross_repo_version_skew", bundle="uw-ios")
2. Query skew:
   palace.code.find_version_skew(bundle="uw-ios", min_severity="minor", top_n=20)

Tunable knobs (`.env`):
- PALACE_VERSION_SKEW_TOP_N_MAX (default 500)

Limitations:
- Compares resolved_version only; declared-constraint skew is followup
- Calendar versions / git-shas / custom schemes classify as 'unknown'
- Renovate "latest version" data and OWASP CVE enrichment are followups
```

## 12. Documentation deliverables

- `docs/runbooks/cross-repo-version-skew.md` — operator runbook
  (env vars, troubleshooting, drift-detection recipes via
  `palace.memory.lookup`).
- `CLAUDE.md ## Extractors` — register `cross_repo_version_skew`
  row + workflow block above.
- `docs/superpowers/plans/2026-05-06-GIM-NN-cross-repo-version-skew.md`
  — TDD plan (next deliverable in same Board+Claude session).

## 13. Out-of-scope cleanups (NOT in this slice)

- F2 Renovate / GitHub-Releases / deps.dev integration — followup.
- F3 OWASP / NVD CVE enrichment — followup.
- F4 declared_constraint skew — followup.
- F1 `:VersionSkew` precomputed nodes — followup if perf demands.

## 14. Risks

| Risk | Mitigation |
|------|------------|
| `packaging.version.parse` lenient enough? Some swift / maven version strings may degrade to `unknown` when intuitively they are semver. | Acceptance #15 ties extractor and tool through shared compute; integration test surfaces real-world UW version-string distribution; tweak parser if a meaningful fraction goes `unknown`. |
| Bundle membership state stale (member listed but `:Project{slug}` absent) | `target_status['stale_slug'] = 'not_registered'`; member skipped from member_count. Operator notices via warning field. |
| GIM-191 schema evolution | Acceptance #14 (pure-read) catches if any property name changes (test fails fast). |
| `:ExternalDependency.purl` may someday include build qualifiers like `pkg:maven/g/a@1.0.0?type=jar` | `split('@')[1]` then second `split('?')[0]` step in `purl_parser` to strip qualifiers; documented as F-future-extend. |
| Multiple `@` in purl (theoretically allowed in URL form) | Use `rsplit('@', 1)` instead of `split('@')[1]`; covered in unit test. |
| Bundle of 100+ members (UW iOS at 41 today; could grow) | UNWIND query at 100×~20 deps = 2000 rows; well within Cypher streaming. Performance SLO 200 ms warm holds. |

---
