---
slug: dead-symbol-binary-surface
status: proposed
branch: feature/roadmap-33-dead-symbol-binary-surface
paperclip_issue: 193
roadmap_item: 33
date: 2026-05-04
authoring_team: Board/Codex brainstorm for CX handoff
base: develop@05fe1b7b0642920a63bd1f4225a12f4d786cccff
plan: docs/superpowers/plans/2026-05-04-roadmap-33-dead-symbol-binary-surface.md
---

# Roadmap #33 - Dead Symbol & Binary Surface Extractor - Spec

## Goal

Design extractor `dead_symbol_binary_surface` that records candidate unused code
and binary-surface reachability facts for Swift and Kotlin/Android modules.

The extractor answers:

- Which indexed declarations are reported unused by static dead-code tooling?
- Which public or binary-visible symbols are retained even when no source
  references are found?
- Which symbols are dead-code candidates with only static evidence, runtime
  evidence, or both?
- Which candidates are safe for review triage, and which are too uncertain to
  suggest deletion?

This slice is a signal extractor, not an auto-delete tool. It must produce
reviewable graph facts with explicit evidence quality and false-positive guards.

## Context

Roadmap row: `docs/roadmap.md` item #33 "Dead Symbol & Binary Surface" owned by
CX, tool stack `Periphery + Reaper SDK + CodeQL`.

Current adjacent work:

- GIM-190 / roadmap #27 Public API Surface is merged and gives exported API
  facts.
- GIM-192 / roadmap #31 Cross-Module Contract is merged on `develop` and proves
  which exported symbols are consumed across modules.
- GIM-191 / roadmap #5 Dependency Surface is in review and is not a hard
  dependency for this slice.
- GIM-186 Git History Harvester is merged on `develop`, but #33 v1 should not
  require historical churn data.

## Reference Basis

Local research lists #33 as heuristic structural extraction based on Periphery,
Reaper, and CodeQL:

- `docs/research/extractor-library/outline.yaml`
- `docs/research/extractor-library/report.md`
- `docs/research/extractor-library/sources.md`

Primary tool assumptions checked on 2026-05-04 and corrected after independent
review:

- Periphery reports unused Swift declarations by building/indexing targets and
  traversing from roots. It warns that incomplete target builds can create false
  positives and supports retaining public declarations for framework-style
  projects. Periphery supports multiple output formats, but this spec does not
  assume a published, versioned JSON schema; Phase 1.1 must freeze the exact
  fixture format before Phase 2. Source: <https://github.com/peripheryapp/periphery>.
- Emerge Reaper is runtime-usage based for iOS and Android. Android requires
  Gradle plugin instrumentation and release-like builds; iOS/Android reports
  upload to Emerge backend/UI. Public docs do not provide an offline
  extractor-readable report file contract, so Reaper is v1 schema-ready/no-op
  only. Sources: <https://docs.emergetools.com/docs/reaper>,
  <https://docs.emergetools.com/docs/reaper-setup-android>,
  <https://docs.emergetools.com/docs/reaper-setup>.
- CodeQL has current Kotlin and Swift support, but CodeQL database builds are
  expensive enough that existing research recommends optional or nightly
  enrichment rather than per-run hard dependency. Sources:
  <https://github.blog/changelog/2026-02-24-codeql-adds-go-1-26-and-kotlin-2-3-10-support-and-improves-query-accuracy/>
  and <https://github.blog/changelog/2026-03-31-codeql-2-25-0-adds-swift-6-2-4-support/>.

## Assumptions

- The extractor ingests pre-generated tool outputs in v1. It does not modify
  production Xcode projects, Gradle projects, or app release pipelines to install
  Reaper or Periphery.
- Phase 1 symbol indexes remain the source of truth for source identity and
  stable symbol correlation.
- GIM-190 `PublicApiSymbol` facts are mandatory in the integration fixture.
  GIM-192 contract facts are mandatory in the integration fixture for the
  blocker guard, even though production runs may skip contract enrichment when
  #31 has not been run for that project/commit.
- Dead-code detection is heuristic. Every graph node must carry evidence source,
  confidence, and skip/reason metadata rather than claiming deletion safety.
- Reaper evidence is schema-ready/no-op in v1 for both iOS and Android. There is
  no fabricated Reaper parser or synthetic "unused class" report unless a real
  exportable artifact contract is verified in a later spec revision.
- Static Periphery fixture evidence is the mandatory Swift path.
- Android/Kotlin dead-code evidence is deferred unless Phase 1.1 explicitly
  selects another file-output-capable tool after a documented spike. Candidates
  include Detekt custom rules and R8/dead-code Gradle plugins such as
  `bye-bye-dead-code`, but choosing one changes the v1 scope.
- UW Compose-first false-positive sources are first-class risks: `@Composable`
  inlining, KotlinX Serialization plugin codegen, generated DI/Compose glue,
  Swift `@objc` / `@objcMembers`, Objective-C runtime exposure, and synthesized
  Codable conformance.

## Scope

### In Scope

- New extractor identity: `dead_symbol_binary_surface`.
- Parser for the Phase 1.1-approved Periphery fixture format. The fixture must
  include `tool_name`, `tool_version`, `output_format`, and
  `tool_output_schema_version`; unknown top-level keys fail parser tests until
  reviewed.
- Reaper schema-ready/no-op skip path for both iOS and Android:
  `reaper_report_unavailable`.
- Optional CodeQL enrichment from pre-generated SARIF or CSV facts; not required
  for the v1 happy path.
- Graph model for dead-symbol candidates, evidence records, and binary-surface
  retention facts.
- Exact correlation from tool findings to Phase 1 `SymbolOccurrence` or
  GIM-190 `PublicApiSymbol` by normalized FQN / symbol qualified name only.
- Safety guards:
  - public exported API is never marked deletion-safe;
  - symbols consumed by #31 per-symbol contract edges are not deletion
    candidates;
  - framework/public APIs require explicit retain-public mode;
  - dynamic entry points and generated code require explicit skip reasons.
- Project-local skiplist support at `.palace/dead-symbol-skiplist.yaml` for
  generated and dynamic entry points.
- Mini fixture with Swift symbols where at least one symbol is unused, one is
  used, one is public-retained, and one is generated/dynamic-skipped.
- Unit tests for parser normalization, correlation, skip reasons, deterministic
  IDs, and confidence scoring.
- Integration test proving Neo4j nodes/edges and idempotent re-runs.
- Runbook with operator smoke for Periphery fixture and optional real-project
  smoke.

### Out Of Scope

- Automatically deleting code or opening cleanup PRs.
- Installing Reaper SDK or Emerge Gradle plugin into UW production projects.
- Running Periphery or CodeQL as part of the extractor process in v1.
- Runtime telemetry collection, backend upload, Emerge account setup, Emerge API
  scraping, reverse engineering the Emerge backend, or PII review for Reaper.
- Cross-commit trend analysis, churn prioritization, or ownership routing.
- Full binary size attribution and linker map parsing.
- Fuzzy matching between tool output and source symbols.
- Public MCP tools or API endpoints.

## Data Model

### `DeadSymbolCandidate`

- `id`: `dead_symbol_id_for(...)`, a 128-bit hex stable hash of `group_id`,
  `project`, `language`, `module_name`, `symbol_key`, `commit_sha`, and
  `evidence_source`.
- `group_id`
- `project`
- `module_name`
- `language`: `swift`, `kotlin`, `java`, or `unknown`.
- `commit_sha`
- `symbol_key`: normalized symbol qualified name when known.
- `display_name`
- `kind`: `class`, `struct`, `enum`, `protocol`, `function`, `property`,
  `initializer`, `typealias`, `unknown`.
- `source_file`
- `source_line`
- `evidence_source`: `periphery`, `reaper`, `codeql`, `synthetic_fixture`.
- `evidence_mode`: `static`, `runtime`, or `hybrid`.
- `confidence`: `low`, `medium`, `high`.
- `candidate_state`: `unused_candidate`, `retained_public_api`,
  `runtime_unseen`, `static_unreferenced`, `skipped`.
- `skip_reason`: nullable, e.g. `public_api_retained`,
  `cross_module_contract_consumed`, `generated_code`, `dynamic_entry_point`,
  `ambiguous_symbol_match`, `missing_symbol_key`.
- `schema_version`

### `BinarySurfaceRecord`

- `id`: stable hash of `group_id`, `project`, `module_name`, `symbol_key`,
  `commit_sha`, and `surface_kind`.
- `group_id`
- `project`
- `module_name`
- `language`
- `commit_sha`
- `symbol_key`
- `surface_kind`: `public_api`, `binary_visible`, `dynamic_entry_point`,
  `framework_retained`.
- `retention_reason`
- `source`: `public_api_surface`, `periphery_retain_public`, `manual_fixture`,
  `codeql`, or `reaper`
- `schema_version`

### Edges

- `(DeadSymbolCandidate)-[:BACKED_BY_SYMBOL]->(SymbolOccurrenceShadow)` when
  exact correlation exists.
- `(DeadSymbolCandidate)-[:BACKED_BY_PUBLIC_API]->(PublicApiSymbol)` when the
  symbol is exported by GIM-190.
- `(DeadSymbolCandidate)-[:HAS_BINARY_SURFACE]->(BinarySurfaceRecord)`.
- `(DeadSymbolCandidate)-[:BLOCKED_BY_CONTRACT_SYMBOL]->(PublicApiSymbol)` when
  GIM-192 proves cross-module consumption through
  `(ModuleContractSnapshot)-[:CONSUMES_PUBLIC_SYMBOL]->(PublicApiSymbol)`.
  The edge must copy the blocking provenance as properties:
  `contract_snapshot_id`, `consumer_module_name`, `producer_module_name`,
  `commit_sha`, `use_count`, and `evidence_paths_sample`.

Do not encode deletion permission as an edge or boolean in v1. Consumers must
interpret `candidate_state`, `confidence`, and blockers.

`schema_version` is a property only. It must not be part of
`DeadSymbolCandidate.id` or `BinarySurfaceRecord.id`; schema bumps must migrate
or rewrite properties without creating a parallel candidate population.

`symbol_id_for(...)` remains only the Phase 1 Tantivy/symbol-index join key. Do
not reuse it for graph node IDs. Add a dedicated `dead_symbol_id_for(...) -> str`
helper that mirrors the 128-bit hex `_stable_id` style used by
`public_api_surface.py`.

## Correlation Rules

1. Exact match only:
   - Periphery/Reaper/CodeQL normalized symbol key equals
     `PublicApiSymbol.symbol_qualified_name`; or
   - normalized symbol key maps to Phase 1 `symbol_id_for(...)`.
2. If multiple source symbols match one tool finding, create no candidate and
   emit `ambiguous_symbol_match`.
3. If no source symbol matches, create a low-confidence candidate only when the
   raw tool output has a stable file path and line; otherwise skip.
4. Any candidate with matching `PublicApiSymbol.visibility in {public, open}`
   becomes `retained_public_api`, not `unused_candidate`.
5. Any candidate with a GIM-192 `CONSUMES_PUBLIC_SYMBOL` edge at the same commit
   becomes blocked with `cross_module_contract_consumed`.
6. Generated code paths and known dynamic entry point patterns are skipped by
   `.palace/dead-symbol-skiplist.yaml`, not hard-coded ad hoc inside parser
   logic.
7. Cross-language matching is forbidden. A Kotlin/Java finding can only match
   Kotlin/Java indexed symbols; a Swift finding can only match Swift indexed
   symbols. Bridge semantics are owned by roadmap #4 and GIM-190/#31 bridge
   fields.

## Affected Files And Areas

Expected implementation paths after approval:

- `services/palace-mcp/src/palace_mcp/extractors/dead_symbol_binary_surface/`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/identifiers.py`
  for `dead_symbol_id_for(...)` only if reviewers prefer a shared helper;
  otherwise keep the helper local in the extractor package.
- `services/palace-mcp/tests/extractors/unit/test_dead_symbol_binary_surface*.py`
- `services/palace-mcp/tests/extractors/integration/test_dead_symbol_binary_surface_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/`
- `docs/runbooks/dead-symbol-binary-surface.md`

Implementation must not modify GIM-190 or GIM-192 semantics except by adding
read-only query helpers with focused regression tests.

## Acceptance Criteria

1. `dead_symbol_binary_surface` is registered and runnable by the extractor
   runner.
2. Periphery fixture ingestion creates `DeadSymbolCandidate` rows for unused
   Swift declarations.
3. Used, public-retained, generated, and dynamic-entry symbols are not emitted
   as deletion candidates.
4. Candidate IDs are deterministic across two identical runs.
5. Exact correlation links at least one candidate to an indexed source symbol.
6. Exported public API symbols become `retained_public_api` with a blocker
   reason, not deletion-safe candidates.
7. GIM-192 contract facts are present in the integration fixture, and consumed
   public symbols are blocked by per-symbol contract evidence.
8. Missing or ambiguous symbol keys are recorded as explicit skips.
9. Integration test proves Neo4j idempotency: unchanged re-run produces
   `nodes_created == 0`, `relationships_created == 0`, and
   `properties_set == 0` for candidates and all four edge families.
10. CodeQL enrichment is optional and can be absent without failing the v1 run.
11. Reaper runtime evidence path is explicitly skipped with a
   `reaper_report_unavailable` metric for both iOS and Android.
12. No public MCP/API tool is added in v1.
13. Fixture includes a symbol that is both public API and consumed by GIM-192,
   proving combined retained-public + contract-blocker behavior.
14. Generated/dynamic skiplist path `.palace/dead-symbol-skiplist.yaml` is
   loaded, validated, and covered by tests.

## Verification Plan

Blocking Phase 1.1 gate before Phase 2:

- Capture Periphery output from a controlled Swift mini fixture and freeze the
  exact parser contract under
  `docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md`.
- CXCodeReviewer must sign off on the fixture format before Phase 2 begins.
- Reaper remains schema-ready/no-op unless a real exportable report contract is
  documented in a spec revision and reviewed again.
- If Android v1 is desired, run a separate spike for Detekt/R8/dead-code Gradle
  plugin output. Do not silently swap tools during implementation.
- Confirm the fixture has a known public symbol so the public-retention guard is
  exercised.

Implementation verification:

- `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface*.py`
- `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_dead_symbol_binary_surface_integration.py -v`
- `cd services/palace-mcp && uv run ruff format --check src tests`
- `cd services/palace-mcp && uv run ruff check src tests`
- `cd services/palace-mcp && uv run mypy src`
- `docker compose --profile review up -d --wait --build`
- Review-profile smoke must paste:
  - JSON response from `palace.ingest.run_extractor`;
  - `MATCH (d:DeadSymbolCandidate) RETURN d.candidate_state, count(*)`;
  - `MATCH (b:BinarySurfaceRecord) RETURN count(b)`;
  - Cypher proof that no `unused_candidate` has a public/open API match or a
    `BLOCKED_BY_CONTRACT_SYMBOL` edge.

## Risks

- Periphery false positives are easy when not all targets are built. v1 must
  store target/build context and never treat static output as deletion proof.
- Future Reaper evidence needs app rollout and can lag behind source changes.
  v1 must not ingest it without a real exportable report contract.
- CodeQL database builds are expensive; making CodeQL mandatory would slow the
  extractor lane and conflict with existing research guidance.
- Public API and dynamic entry points can look unused statically. Guards from
  GIM-190 and GIM-192 are mandatory when available.
- Swift generic and Objective-C limitations can create incomplete runtime
  evidence. Those must downgrade confidence rather than fail the run.
- Periphery false positives can come from Swift `@objc` / `@objcMembers`,
  NSObject inheritance, synthesized Codable properties, Interface Builder,
  XCTest subclasses, and external modules.
- Kotlin/Android false positives can come from KotlinX Serialization generated
  code, Compose compiler inlining, reflection, R8 keep rules, KSP/KAPT-generated
  sources, and DI framework entry points.
- Concurrent extractor runs can race on MERGE paths if the writer uses bare
  autocommit calls. Phase 2 must choose an `execute_write` transaction boundary
  or prove why per-statement writes are safe.

## Open Questions

1. Should v1 remain Swift/Periphery-only plus Reaper no-op, or should Android be
   added through a separate Detekt/R8/dead-code Gradle plugin spike?
2. Should public API retention use GIM-190 only, or also parse Periphery
   `--retain-public` configuration as a first-class `BinarySurfaceRecord`?
3. Should `.palace/dead-symbol-skiplist.yaml` be mandatory for production
   project runs, or optional with a built-in empty default?
4. Should CodeQL enrichment be included in Phase 2 implementation or explicitly
   deferred to a nightly follow-up?
5. Should candidate confidence be a simple enum in v1 or derived from a scored
   evidence matrix?
