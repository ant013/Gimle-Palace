---
title: Cross-repo version skew extractor — pure skew detection over GIM-191 :DEPENDS_ON
slug: cross-repo-version-skew
date: 2026-05-06
status: proposed (rev2)
paperclip_issue: GIM-218
predecessor_sha: 0a9c2363a
authoring: Board+Claude
team: Claude
roadmap_item: "#39 Cross-Repo Version Skew"
roadmap_source: "docs/roadmap.md §2.1 Structural, row #39 (verified 2026-05-06 by Board+Claude after GIM-191 dependency_surface merged 2026-05-04)"
---

# Cross-repo version skew extractor (Roadmap #39)

## rev2 changelog (2026-05-06)

Operator pre-CR review across 4 independent agents (Architect / Security
/ Silent-failure / Performance) surfaced 3 correctness issues + 13
material gaps. Rev2 closes them. Skipped items are listed at bottom.

- **C1 (substrate alignment, Architect)** — rev1 wrote `:IngestRun{source='extractor.cross_repo_version_skew'}`.
  Substrate writer (`foundation/checkpoint.py:create_ingest_run`) uses
  property `extractor_name`, value is the bare name (e.g.,
  `'dependency_surface'`, no `extractor.` prefix). All references to
  `source` and the `'extractor.<name>'` value pattern updated to use
  `extractor_name` and `'cross_repo_version_skew'`. Note: CLAUDE.md
  "Known limitations" doc independently has the same misnomer; that's
  a CLAUDE.md doc-bug, not a spec problem, and is left to a separate
  doc-fix PR. The same misnomer also exists in the sibling GIM-216
  code-ownership spec (in CTO Phase 1.1 review); flag for that spec's
  own rev2.
- **C2 (project-mode honesty, Architect)** — Architect verified
  against `dependency_surface/parsers/gradle.py`: Gradle parser
  resolves all aliases through a single `libs.versions.toml`, so
  every module sees the same version per alias. SPM and Python are
  single-manifest per project. Therefore project-mode finds no
  intra-project skew **for projects whose dependencies all flow
  through the canonical alias / lockfile mechanism** — which is the
  common UW Android case. Project-mode is retained because
  (a) some Gradle projects bypass the alias and write raw
  `implementation("g:a:1.5")` constraints which a future
  `dependency_surface` parser extension would surface;
  (b) project-mode is structurally identical to bundle-mode-of-1 so
  costs nothing extra to keep. §13 documents this as a known
  limitation; §3 R3 expanded with the rationale; §11 operator
  workflow includes a warning that for canonical-Gradle UW Android
  the meaningful target is `bundle="uw-android"` (with one member),
  not `project="uw-android"` (which today returns the same).
- **C3 (use writer-stored properties, Architect)** — rev1 Cypher
  did `split(d.purl, '@')[1]` and
  `split(split(d.purl, ':')[1], '/')[0]` to extract version and
  ecosystem. GIM-191 writer already stores both as properties
  (`d.resolved_version`, `d.ecosystem`). §5 Cypher rewritten to read
  the properties directly. `purl_parser.py` shrinks to one helper
  (`purl_root_for_display(purl) → purl[: purl.rfind('@')]`); the
  ecosystem-extraction logic disappears. Resolves the
  `pkg:generic/spm-package?vcs_url=...@<version>` corner case from
  rev1 §14 — qualifier-bearing purls no longer mis-split.
- **S1 (trust model, Security)** — added §1.1 Trust model
  subsection. States caller is in-process MCP client,
  group_id-scoped operations are enforced via existing substrate,
  tool does NOT accept arbitrary Cypher.
- **S2 (slug enumeration oracle, Security)** — `target_status` map
  refined: when caller's session is unauthenticated for a target
  (future MCP auth gate; today trivially "true"), the three states
  (`not_registered` / `not_indexed` / `indexed`) collapse to a
  single `unavailable` value. Within the caller's authorized scope,
  full status is preserved. v1 single-tenant deployment treats all
  callers as authorized, so behavior unchanged at runtime; the
  contract is in place for multi-tenant future.
- **S3 (bundle slug regex, Security)** — explicit slug regex
  validation for `bundle=` arg (uses existing `_SLUG_RE` pattern).
  `resolve_targets()` Phase 0 also re-validates every member slug
  returned by `bundle_members()`; invalid members → `target_status[slug] = 'invalid_slug'`,
  not passed to Cypher.
- **S4 (ecosystem enum single source, Security)** — `EcosystemEnum`
  in `models.py` is the single source of truth. Both validator
  (§7) and acceptance test for cocoapods reference the enum
  literally. cocoapods is currently NOT in v1 enum → caller gets
  `invalid_ecosystem_filter` (consistent fail-closed).
- **S5 (top_n bounds, Security)** — explicit lower bound `1` for
  `top_n` in §7. Env var `PALACE_VERSION_SKEW_TOP_N_MAX` validated
  at startup: must be `>= 1`; misconfig → fail-fast at extractor
  registration time, not at first tool call.
- **SF1 (empty-bundle distinction, Silent-failure)** —
  `bundle_not_registered` (`:Bundle{name}` doesn't exist) split
  from new code `bundle_has_no_members` (node exists,
  `:HAS_MEMBER` count is 0). §7 + §8 + §9 acceptance updated.
- **SF2 (purl-format guard, Silent-failure)** — Cypher §5
  unconditionally filters `WHERE d.purl STARTS WITH 'pkg:'`.
  Malformed purls excluded; `:IngestRun.warnings_purl_malformed_count`
  bumps; warning entry surfaced in tool envelope.
- **SF3 (single-source-of-truth regression gate, Silent-failure)** —
  `_compute_skew_groups()` is now the only place that can call the
  aggregation Cypher. Acceptance #15 strengthened: a unit test in
  `tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py`
  greps the package source for any other module that contains
  `MATCH (p:Project` AND `:DEPENDS_ON` patterns; fails CI on hit
  (with explicit `# noqa: skew-compute` opt-out for sanctioned cases).
- **SF4 (warnings schema, Silent-failure)** — `warnings[]` field in
  success envelope and `:IngestRun` is now a typed list of
  `{code: str, slug: str | None, message: str}` where `code` is one
  of: `member_not_indexed`, `member_not_registered`,
  `member_invalid_slug`, `purl_missing_version`, `purl_malformed`,
  `version_unparseable_in_group`. §3 envelope spec'd, §10
  acceptance updated.
- **P2 (index dependency, Performance)** — §5 explicit note: the
  bundle-mode `UNWIND` performance assumes the
  `:Project{slug} IS UNIQUE` constraint installed by GIM-191
  substrate (`palace.memory.register_project`). Without it the
  query degrades to AllNodesScan × member_count.
- **P5 (query timeout, Performance)** — added env var
  `PALACE_VERSION_SKEW_QUERY_TIMEOUT_S` (default 30, range
  `[1, 600]`), passed to Bolt session. Runaway queries fail
  with `extractor_runtime_error` rather than block the event loop.
- **I2 wording fix** — rev1 §3 R6 said `include_aligned=False` is
  "opt-in via `include_aligned=False`" — that's opt-OUT. Reworded:
  "aligned groups are excluded by default; opt **in** via
  `include_aligned=True`."
- **I6 severity rank ordering** — `severity_rank` defined
  explicitly in §3 and in the sort logic: `major=3, minor=2,
  patch=1, unknown=0`. `min_severity='major'` returns rank ≥ 3 →
  excludes `unknown`. To request unknown-only, caller passes
  `min_severity='unknown'` (matches and includes everything ≥0,
  but defaults to None == all severities). Documentation and one
  acceptance test added.

**Skipped (operator triage)**:
- Sibling spec verification (Security HIGH about §1 referencing the
  GIM-216 spec by floating filename): rephrased the §8 PII rule
  inline so it doesn't depend on the sibling being on disk; the
  cross-reference becomes an aspirational link, not load-bearing.
- "Cypher injection guard" invariant (S6 LOW): added one bullet in
  §8 ("All Cypher params are bound; mode selection chooses a
  constant query string") rather than a dedicated section. Read-only
  tool over indexed graph data; over-engineering risk.
- Drift fingerprint (M2 silent-failure): `:IngestRun` extras already
  carry per-severity counts; that's enough for v1 drift detection
  via `palace.memory.lookup` count comparison. Content-diff is F1.
- `version_unparseable` separate severity (M3 silent-failure):
  `unknown` is sufficient; warnings counter
  `version_unparseable_in_group` exposed via `warnings[]` per SF4.
- CI perf regression check (P3 INFO): smoke is manual on iMac, same
  pattern as other extractors. v1 ships without CI perf gate.
- Cold-cache SLO (P3 LOW): manual smoke is acceptable cadence; spec
  states warm SLO as soft target.
- `purl_format_invalid` and `version_filter_unparseable` proposed
  error codes (Silent-failure missing-codes section): both folded
  into the `warnings[]` schema (SF4) rather than top-level errors,
  since they're informational.

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

## 1.1 Trust model

- **Caller**: in-process MCP client connected to palace-mcp's event
  loop. v1 deployment is single-tenant or trusted-team
  (per `project_palace_purpose_unstoppable.md`); multi-tenant
  isolation enforcement is a broader palace-mcp slice, not blocking
  #39.
- **Authorization scope**: the tool operates on
  `group_id = "project/<slug>"` for project-mode and
  `group_id = "bundle/<name>"` for bundle-mode, mirroring existing
  substrate scoping. No tenant isolation is currently enforced
  beyond what the underlying graph reads; if a future ACL slice
  lands, this tool inherits it via the unmodified Cypher contract.
- **Cypher safety**: the tool does NOT accept arbitrary Cypher.
  Mode selection chooses one of two constant-string queries (§5);
  user inputs (`slug`, `bundle`, `ecosystem`, `member_slugs`) are
  always bound parameters, never templated. §8 idempotency invariant
  enforces this.
- **Slug enumeration oracle (Security S2 mitigation)**: in v1
  single-tenant deployment, all callers are authorized for all
  projects. The `target_status` map collapses three states
  (`not_registered` / `not_indexed` / `indexed`) to `unavailable`
  ONLY for targets outside the caller's authorized scope (a future
  multi-tenant gate). Today this collapse is trivial — no targets
  are out-of-scope. Documented now so multi-tenant landing is a
  contract change, not a privacy regression.
- **Supply-chain composition**: dependency data is technically
  public for FOSS components, but pinning patterns can leak
  proprietary fork existence. Treat `find_version_skew` output as
  business-confidential in deployments where the `:ExternalDependency`
  graph might include private forks.

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
- Substrate-aligned `:IngestRun{extractor_name='cross_repo_version_skew'}`
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
  `palace.memory.lookup(filters={extractor_name='cross_repo_version_skew',
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
  **Known limitation for canonical-Gradle projects (per Architect C2
  audit, verified against `dependency_surface/parsers/gradle.py`):**
  Gradle parser resolves all aliases through one `libs.versions.toml`,
  so for projects whose dependencies all flow through aliases, every
  module sees the same resolved version. Project-mode finds zero
  intra-module skew on such projects. Same applies to SPM and
  Python (single-manifest per project). Project-mode remains
  meaningful for: (a) projects mixing alias and raw
  `implementation("g:a:1.5")` calls (a future
  `dependency_surface` parser extension would surface this);
  (b) consistency: project-mode is structurally identical to
  bundle-mode-of-1 — costs nothing extra. Operators querying UW
  Android today should use `bundle="uw-android"` (single-member
  bundle) for forward compatibility; results identical to
  `project="uw-android"` until #39's parser-extension followup
  lands.

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
  (opt **in** to inclusion via `include_aligned=True`). top_n=50,
  range [1, 500]. Default `min_severity=None` returns all severities
  (incl. `unknown`); operator filters as needed.

  **Severity rank order (per Architect I6):** `severity_rank`
  is explicitly defined as
  `{'major': 3, 'minor': 2, 'patch': 1, 'unknown': 0}`. Filter
  `min_severity='major'` returns groups with rank >= 3 → excludes
  `unknown` and lower. `min_severity='unknown'` includes everything
  (rank >= 0). Default `min_severity=None` returns all severities
  unfiltered (semantically equivalent to `'unknown'` but skips the
  filter expression for clarity). Sort uses this same rank for the
  `severity desc` term.

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
    "warnings": [                               # SF4 schema (typed, never freeform strings)
        # {"code": "member_not_indexed", "slug": "NavigationKit", "message": "..."},
        # {"code": "purl_malformed", "slug": null, "message": "27 :ExternalDependency rows lack pkg: prefix"},
    ],
    "last_run_at": "2026-05-06T...",
    "last_run_id": "uuid-...",
}
```

**`warnings[]` schema** (per Silent-failure SF4):

| Field | Type | Note |
|-------|------|------|
| `code` | str | one of: `member_not_indexed`, `member_not_registered`, `member_invalid_slug`, `purl_missing_version`, `purl_malformed`, `version_unparseable_in_group` |
| `slug` | str \| null | per-target slug for `member_*` codes; null for graph-wide (`purl_*`, `version_*`) |
| `message` | str | human-readable, ≤256 chars; never includes raw email/secret/full Cypher rows |

This is a closed enum. New warning kinds require a spec/code change,
not freeform string injection. v1 enforces via Pydantic `Literal[...]`
on `WarningEntry` model.

**Sort order**: `(severity_rank desc, version_count desc, purl_root asc)`.
This is a total order over result rows because `purl_root` is the
group key — no two output rows share the same `purl_root` (per
Architect P1 clarification). Severity rank values are explicit per
§3 R6.

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

GIM-191 writer (`dependency_surface/neo4j_writer.py`) stores
`d.ecosystem` and `d.resolved_version` as first-class properties
on `:ExternalDependency`. We read them directly — no string surgery
on `d.purl`. `purl_root` for display is computed as
`d.purl[: d.purl.rfind('@')]` in Python, after fetch.

The `WHERE d.purl STARTS WITH 'pkg:'` guard (per SF2) excludes
malformed purls; the matching count surfaces as
`warnings[code='purl_malformed']` in the response.

**Project-mode** (intra-module via `r.declared_in`; see §13 known
limitation about Gradle-alias-only projects):

```cypher
MATCH (p:Project {slug: $slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WHERE d.purl STARTS WITH 'pkg:'
  AND d.resolved_version IS NOT NULL
  AND ($ecosystem IS NULL OR d.ecosystem = $ecosystem)
RETURN d.purl                         AS purl,
       d.ecosystem                    AS ecosystem,
       d.resolved_version             AS version,
       r.declared_in                  AS scope_id,
       r.declared_in                  AS declared_in,
       r.declared_version_constraint  AS declared_constraint
ORDER BY d.purl, scope_id
```

**Bundle-mode** (cross-member via `:Bundle{name}`-resolved members):

```cypher
UNWIND $member_slugs AS slug
MATCH (p:Project {slug: slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WHERE d.purl STARTS WITH 'pkg:'
  AND d.resolved_version IS NOT NULL
  AND ($ecosystem IS NULL OR d.ecosystem = $ecosystem)
RETURN d.purl                         AS purl,
       d.ecosystem                    AS ecosystem,
       d.resolved_version             AS version,
       p.slug                         AS scope_id,
       r.declared_in                  AS declared_in,
       r.declared_version_constraint  AS declared_constraint
ORDER BY d.purl, scope_id
```

The two queries differ only in the `MATCH` (single project vs UNWIND)
and `scope_id` source (`r.declared_in` vs `p.slug`). `_compute_skew_groups()`
selects the right query based on mode.

A separate diagnostic query runs once per Phase 2 to count purls
that failed the `pkg:` guard, used to populate the
`warnings[code='purl_malformed']` aggregate:

```cypher
MATCH (p:Project)-[:DEPENDS_ON]->(d:ExternalDependency)
WHERE NOT d.purl STARTS WITH 'pkg:'
  AND p.slug IN $target_slugs
RETURN count(*) AS malformed_count
```

### Indexes / constraints

None new. Substrate `:IngestRun.run_id` UNIQUE constraint exists.

**Performance dependency on existing indexes (P2):**
- `:Project{slug}` UNIQUE — installed by `palace.memory.register_project`
  substrate. Bundle-mode `UNWIND $member_slugs AS slug MATCH (p:Project {slug: slug})`
  uses `NodeIndexSeek` per slug under this constraint. Without it, the
  query falls back to `AllNodesScan + Filter` per UNWIND iteration —
  41 × O(N) for UW iOS bundle. The schema_extension does NOT
  re-create this constraint; it's a precondition. `Phase 0` ASSERT
  test validates the constraint exists at extractor startup; if
  missing, fail-fast with `extractor_runtime_error: project_slug_index_missing`.
- `:ExternalDependency{purl}` UNIQUE — owned by GIM-191. Used
  implicitly through the relationship traversal; not required for
  correctness, only for write-time idempotency in GIM-191.

## 6. Configuration (env vars)

Added to `PalaceSettings` (`config.py`), prefix `PALACE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PALACE_VERSION_SKEW_TOP_N_MAX` | `500` | Upper bound for `top_n` arg. Validated at startup: must be `>= 1` AND `<= 10000`; out-of-startup-range → fail-fast at registration. Per-call out-of-bound (`top_n` outside `[1, env_max]`) → `top_n_out_of_range`. |
| `PALACE_VERSION_SKEW_QUERY_TIMEOUT_S` | `30` | Bolt session timeout for the aggregation Cypher (seconds). Range `[1, 600]` validated at startup. Runaway query → tx kill → `extractor_runtime_error` with `error_message="query_timeout_<seconds>s"`. |

Reused: `PALACE_RECENCY_DECAY_DAYS` is **not** used (no time-decay
component). Substrate Tantivy caps (`PALACE_MAX_OCCURRENCES_*`) do
**not** apply (no Tantivy writes).

## 7. MCP tool error envelopes

| `error_code` | Trigger | Resolution-order rank |
|--------------|---------|------------------------|
| `top_n_out_of_range` | `top_n` outside `[1, PALACE_VERSION_SKEW_TOP_N_MAX]` | 1 (validate before any DB hit) |
| `slug_invalid` | bad slug regex on `project=` arg | 1 |
| `bundle_invalid` | bad slug regex on `bundle=` arg | 1 |
| `mutually_exclusive_args` | both `project=` and `bundle=` non-null | 1 |
| `missing_target` | both `project=` and `bundle=` null | 1 |
| `invalid_severity_filter` | `min_severity ∉ {None, 'patch', 'minor', 'major', 'unknown'}` (validated against `SeverityEnum` in models.py) | 1 |
| `invalid_ecosystem_filter` | `ecosystem ∉ EcosystemEnum.values` (single source `models.py:EcosystemEnum`; v1 = `{'github', 'maven', 'pypi'}`) | 1 |
| `project_not_registered` | `(:Project{slug})` does not exist (project-mode); see §1.1 trust note about future foreign-group collapse | 2 |
| `bundle_not_registered` | `(:Bundle{name})` does not exist (bundle-mode) | 2 |
| `bundle_has_no_members` | `:Bundle{name}` exists but `count(:HAS_MEMBER) = 0` (per Silent-failure SF1 — distinct remediation: caller needs `add_to_bundle`, not `register_bundle`) | 2 |
| `dependency_surface_not_indexed` | for ALL targets `count((p)-[:DEPENDS_ON]) = 0` | 3 |

`target_status` map is **always** populated in the success envelope.
Each target gets one of: `indexed` / `not_indexed` / `not_registered`
/ `invalid_slug` / `unavailable` (the last reserved for future
multi-tenant foreign-group queries; in v1 single-tenant deployment
never appears at runtime — see §1.1).

Informational warnings appear when ≥1 but <all targets are indexed
(per SF4 schema, see §3 envelope).

### Slug regex (single source)

The same `_SLUG_RE` pattern from substrate is reused for both
`project=` and `bundle=` validation:

```python
import re
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
```

Member slugs returned by `palace.memory.bundle_members()` are
re-validated in `Phase 0 resolve_targets()`. Invalid members do
NOT enter the Cypher param list; instead they appear in
`target_status[member_slug] = 'invalid_slug'` and a `warnings[code='member_invalid_slug']`
entry is added to the response.

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
   total order over result rows.
4. **Stale `:IngestRun.skew_groups_total` is design intent**, not
   inconsistency. The MCP tool always recomputes live; the
   `:IngestRun` snapshot exists only for between-runs observability.
5. **All Cypher params are bound.** Mode selection (project vs
   bundle) chooses one of two constant-string queries. User
   inputs (`slug`, `bundle`, `ecosystem`, `member_slugs`) flow as
   bind parameters only. No f-string / `.format()` over Cypher
   strings anywhere in the package — enforced by SF3 source-grep
   regression test.

### Edge cases

| Case | Behavior |
|------|----------|
| Project has 0 `:DEPENDS_ON` (new repo, dependency_surface not yet run) | Project mode: `dependency_surface_not_indexed`. Bundle mode: `target_status[slug] = 'not_indexed'`; if ANY member is indexed → success-with-warning (`code='member_not_indexed'`); if ALL → fail. |
| Empty bundle (`:Bundle{name}` exists but `:HAS_MEMBER` count = 0) | (per SF1) `bundle_has_no_members` (distinct from `bundle_not_registered`). Operator remediation: `palace.memory.add_to_bundle`. |
| `d.purl` does not start with `pkg:` (malformed; GIM-191 invariant violated) | (per SF2) Cypher main query excludes via `WHERE d.purl STARTS WITH 'pkg:'`; diagnostic count query bumps `warnings[code='purl_malformed']` aggregate; no individual rows leaked into output. |
| Single-source dep (only 1 scope pins it) | After client-side grouping, groups with `len(distinct_versions) < 2` are excluded from skew output. Counted in `aligned_groups_total` only when `include_aligned=True`. |
| `:ExternalDependency.resolved_version` is null/empty | Cypher filter `d.resolved_version IS NOT NULL`; row excluded; warning `code='purl_missing_version'` aggregated per project. |
| One scope_id with multiple versions of same lib (semantically suspicious — usually a manifest write race in GIM-191) | Group keeps both entries; tool surfaces them as separate rows under one `scope_id`. Not a failure; let the data speak. |
| Bundle with stale member (slug listed in `:HAS_MEMBER` but no `:Project{slug}`) | `target_status[stale_slug] = 'not_registered'` after first `MATCH (p:Project{slug: stale_slug})` returns empty; member excluded from member_count for skew computation; warning `code='member_not_registered'` added. |
| Bundle with member that has invalid slug from `bundle_members()` (somehow corrupted) | `target_status[bad_slug] = 'invalid_slug'` after S3 regex re-validation; member excluded from Cypher; warning `code='member_invalid_slug'` added. |
| `ecosystem` filter passes a value not in `EcosystemEnum` (e.g., `'cocoapods'` in v1) | `invalid_ecosystem_filter` error code fail-fast (per S4 single source). |
| `:ExternalDependency.ecosystem` value matches no real ecosystem (writer regression) | Row passes the `WHERE ($ecosystem IS NULL OR d.ecosystem = $ecosystem)` filter only if caller passed that exact unknown value as `ecosystem=`. Default unfiltered query includes the row. Caller filtering by enum gets normal behavior. |
| Versions `"1.5.0"` and `"1.5"` (parse-equivalent under `packaging.version`) | **Reported as skew** because grouping uses raw-string distinctness (`set(row.version for row in group)` keeps both). When ALL pairs in a group parse identically, severity = `unknown` (no semver delta available); warning `code='version_unparseable_in_group'` added so the operator can distinguish "real semver skew with unknown delta" from "manifest-text-only divergence". Operator can hide via `min_severity='patch'` (which excludes `unknown` per §3 R6 rank). |
| Multiple `@` in `purl` (theoretically allowed in URL-encoded form) | `purl_root_for_display` uses `purl[: purl.rfind('@')]` (rsplit semantics). Unit test asserts `pkg:maven/g/a@b@1.0.0` → root=`pkg:maven/g/a@b`, version=`1.0.0`. |
| Caller passes `min_severity='unknown'` | Returns all groups with rank >= 0 (all of them). Distinct from `min_severity=None` (no filter), which is observationally identical but skips the filter expression. |

### PII discipline

This extractor does NOT touch `:Author` or any email-bearing nodes.
No PII surface. `error_message` and INFO logs reference paths,
SHAs, and slugs only — same hard rule as GIM-216 §8 carries.

## 9. Acceptance criteria

A successful run + tool query produces, given a project / bundle with
`dependency_surface` already indexed:

1. **Extractor bootstrap completes for project-mode.** Run with
   `ctx.project='uw-android'`; `:IngestRun{extractor_name='cross_repo_version_skew',
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

18. **Single-source-of-truth regression gate (SF3).** A unit test
    `tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py`
    greps `services/palace-mcp/src/palace_mcp/` for any non-test file
    other than `extractors/cross_repo_version_skew/compute.py` that
    contains all of: `MATCH`, `Project`, `DEPENDS_ON`. Failure = a
    second module is computing skew. Maintainers can opt out per
    file via `# noqa: skew-compute` (audited).

19. **`bundle_has_no_members` distinct error (SF1).** Test seeds
    `:Bundle{name='empty-bundle'}` with no `:HAS_MEMBER` →
    `find_version_skew(bundle='empty-bundle')` returns
    `error_code='bundle_has_no_members'`, NOT
    `bundle_not_registered`.

20. **Malformed-purl guard (SF2).** Test seeds a `:Project` with
    one normal dep and one
    `:ExternalDependency{purl='broken-format-no-pkg-prefix@1.0.0'}`
    → tool response includes both: 0 skew_groups (or 1 from the
    valid dep paired with another) and
    `warnings=[{code: 'purl_malformed', slug: null,
    message: contains '1' for the count}]`. The malformed row is
    NOT in `entries`.

21. **Severity rank (I6) ordering.** Test calls
    `find_version_skew(...,min_severity='unknown')` returns same
    set as `min_severity=None` (full); `min_severity='major'`
    returns subset (rank ≥ 3); `min_severity='patch'` excludes
    `unknown` (rank 0). Verifies enum order.

22. **Trust model: cypher params are bound (S6 inline).** A unit
    test greps the `cross_repo_version_skew/` package source for
    f-string-templated Cypher (`f"MATCH"`, `.format(`); zero
    occurrences. Acceptance covers the §8 invariant 5.

23. **Query timeout (P5).** Integration test with synthetic
    artificially-slow Bolt mock or a Cypher with `apoc.util.sleep`
    in compute → tool fails with
    `error_code='extractor_runtime_error'`,
    `error_message` contains `query_timeout_<seconds>s`. (Skip if
    apoc not available; document deferred.)

24. **`warnings[]` schema (SF4).** Integration test seeds a fixture
    with a stale bundle member (`:HAS_MEMBER` referencing a
    non-existent slug) → response `warnings` contains exactly one
    entry with `code='member_not_registered'`, valid Pydantic
    structure (no extra fields, no missing fields).

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
- Project-mode for canonical-Gradle / SPM / Python projects finds no
  intra-module skew (aliases resolve through one lockfile per project).
  For UW Android today, prefer `bundle="uw-android"` (single-member
  bundle) for forward compatibility.
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
- `docs/superpowers/plans/2026-05-06-GIM-218-cross-repo-version-skew.md`
  — TDD plan (next deliverable in same Board+Claude session).

## 13. Known limitations (in v1; documented for users)

- **Project-mode is structurally identical to bundle-mode-of-1
  for canonical-Gradle, SPM, and Python projects** (per Architect
  C2 audit, 2026-05-06). Reasoning verified against
  `dependency_surface/parsers/gradle.py`: aliases resolve through
  one `libs.versions.toml`, so all modules see the same version.
  SPM has one `Package.swift`; Python has one `pyproject.toml`.
  Project-mode finds no intra-module skew on these projects.
  **Today, prefer bundle-mode of size 1 for forward
  compatibility.** A future `dependency_surface` parser
  extension may surface raw-constraint usage (`implementation("g:a:1.5")`
  bypassing alias) — at that point, project-mode becomes
  meaningful for those projects without spec changes here.
- **Versions parse-equivalent under `packaging.version` are
  reported as skew with severity `unknown`** (or `patch` if
  classify can't decide). Per §8 edge cases — favors
  manifest-text divergence visibility over post-parse
  equivalence.
- **No CVE / latest-version enrichment** — F2/F3/F8 explicitly
  out of scope.
- **No drift content-diff** — F6 supports count-drift only via
  `palace.memory.lookup` over `:IngestRun.skew_groups_total`.
  Caller must re-run to see WHICH purls changed.

## 13.1 Out-of-scope cleanups (NOT in this slice)

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
