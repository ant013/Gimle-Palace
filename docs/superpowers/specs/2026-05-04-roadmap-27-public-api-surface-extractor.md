# Roadmap #27 - Public API Surface Extractor - Spec Brainstorm

**Status:** CX spec brainstorm, 2026-05-04. Pre-formalization Board draft; not approved for Phase 1.2 implementation.
**Roadmap item:** #27 Public API Surface Extractor.
**Branch:** `feature/GIM-027-public-api-surface-spec`.
**Base:** `develop@f2696fa04147a3976df3228451f9e771628e2e94`.
**Owner:** CX/Codex team.
**Predecessors:** Phase 1 launch-critical implementation rows are merged: GIM-128, GIM-184, and GIM-182.

## Goal

Design a deterministic extractor that records the exported public API surface of UW modules as graph entities that can be queried by module, language, symbol kind, visibility, source artifact, and commit.

The extractor answers questions like:

- Which public types/functions/properties does module `X` export at commit `Y`?
- Which public API entries are undocumented or untested by downstream extractors?
- Which exported symbols are Kotlin-to-Swift bridge surface rather than native Swift/Kotlin declarations?
- Which exported API entries are backed by indexed source symbols from Phase 1 symbol indexes?

This is **not** the breaking-change diff extractor. Roadmap #31 Cross-Module Contract Extractor owns version-to-version API diffing and breaking-change classification. #27 produces the current or versioned public surface snapshots that #31 can consume later.

## Why Now

The CX launch-critical language-indexing lane is closed:

- GIM-128 provides Swift symbol visibility through canonical SCIP output.
- GIM-184 provides C/C++ native symbol visibility through `scip-clang`.
- GIM-182 provides multi-repo SPM bundle registration so first-party HS Kits can be resolved as one ecosystem.

That makes #27 a good first Phase 2 CX spec because it builds on the merged symbol substrate and creates shared schema for later #31, #37, and #28 work.

## Source Basis

Existing repo research already identifies #27 as a deterministic structural extractor:

- `docs/research/extractor-library/outline.yaml`
- `docs/research/extractor-library/report.md`
- `docs/research/extractor-library/results/Cross_Module_Contract_Extractor.json`

External tool assumptions checked for this brainstorm:

- JetBrains Kotlin binary-compatibility-validator exposes `apiDump` and `apiCheck`, and its README currently says it is in maintenance mode while support for current Kotlin versions continues. KLib ABI support remains experimental and must be opt-in.
- Swift API surface extraction remains toolchain-sensitive. `swift package diagnose-api-breaking-changes` is backed by `swift-api-digester`, but recent Swift Forums discussion still shows edge cases around API/ABI semantics and `package` visibility. The spec should hard-gate Swift input choice with smoke evidence before implementation.
- SKIE is useful only when KMP bridge artifacts are present. #27 should treat SKIE overlay data as optional enrichment, not a mandatory v1 dependency.

Primary references:

- Kotlin binary-compatibility-validator: https://github.com/Kotlin/binary-compatibility-validator
- Kotlin binary-compatibility-validator docs: https://kotlin.github.io/binary-compatibility-validator/
- SwiftPM `diagnose-api-breaking-changes` discussion: https://forums.swift.org/t/swift-package-diagnose-api-breaking-changes/54308
- Swift `package` visibility discussion for API diagnostics: https://forums.swift.org/t/diagnose-api-breaking-changes-and-package-scoped-symbols/82881
- SKIE project page: https://skie.touchlab.co/

## Assumptions

- v1 implementation should ingest **pre-generated API surface artifacts** instead of mutating production Gradle or Xcode projects during palace-mcp extraction.
- Existing Phase 1 symbol indexes remain the source of truth for precise source locations and symbol occurrence search.
- #27 owns exported-surface facts, not call graphs, consumer impact, semantic diff rules, binary reachability, or documentation quality.
- Kotlin/JVM and Swift are the v1 priority languages because they cover UW Android/Kotlin, UW iOS Swift, and HS Kit public surfaces.
- KLib/KMP and SKIE support should be designed but smoke-gated because tool support and UW adoption vary by module.
- C/C++ public ABI export is out of v1 unless the operator explicitly asks for native library ABI work. GIM-184 gives native source symbols, not stable library ABI surface.

## Scope

### In Scope

- New extractor design: `public_api_surface`.
- Data model for public API snapshot and public API symbol entities.
- Kotlin public API ingestion from JetBrains binary-compatibility-validator `.api` dumps.
- Swift public API ingestion from a smoke-selected artifact path:
  - preferred candidate: compiler-emitted `.swiftinterface` files when available;
  - alternate candidate: `swift-api-digester` / SwiftPM API diagnostics output when it proves stable on the smoke fixture.
- Optional SKIE bridge overlay ingestion when a KMP module emits SKIE artifacts.
- Correlation from `PublicApiSymbol` to Phase 1 `SymbolOccurrenceShadow` where `symbol_qualified_name` or normalized FQN matches.
- Fixtures that include at least one Kotlin module and one Swift module with public/internal/private declarations.
- Unit tests for parsers, canonical IDs, visibility filtering, signature hashing, and generated/bridge filtering.
- Integration tests proving Neo4j graph nodes/edges and MCP query paths over the public surface.

### Out Of Scope

- Breaking-change classification between two versions. That belongs to #31.
- Consumer impact and cross-module import analysis. That belongs to #31/#45.
- Documentation coverage scoring. That belongs to #37.
- Coverage-gap scoring. That belongs to #28.
- Dead public symbol reachability. That belongs to #33.
- Automatically editing UW Gradle/Xcode project files to install API dump tooling.
- Guaranteed KLib ABI support before smoke evidence.
- Objective-C, Objective-C++, and C/C++ ABI extraction.

## Proposed Model

### Entity Nodes

`PublicApiSurface`

- `id`: stable hash of project, module, language, commit, artifact path, and tool source.
- `project`
- `module_name`
- `language`: `kotlin`, `swift`, or later `unknown`.
- `commit_sha`
- `artifact_path`
- `artifact_kind`: `kotlin_bcv_api`, `swiftinterface`, `swift_api_digester`, `skie_overlay`.
- `tool_name`
- `tool_version`
- `generated_at`
- `schema_version`: initial value `1`.

`PublicApiSymbol`

- `id`: stable hash of project, module, language, normalized FQN, signature hash, and artifact kind.
- `project`
- `module_name`
- `language`
- `fqn`
- `display_name`
- `kind`: `class`, `struct`, `enum`, `protocol`, `interface`, `function`, `method`, `property`, `initializer`, `typealias`, `extension`, `unknown`.
- `visibility`: `public`, `open`, `protected`, `published_api_internal`, `package`, `unknown`.
- `signature`
- `signature_hash`
- `source_artifact_path`
- `source_line`: nullable.
- `is_generated`
- `is_bridge_exported`
- `bridge_source`: nullable, e.g. `skie`.
- `symbol_qualified_name`: nullable correlation key into Phase 1 symbol indexes.
- `schema_version`: initial value `1`.

### Edges

- `(PublicApiSurface)-[:EXPORTS]->(PublicApiSymbol)`
- `(PublicApiSymbol)-[:BACKED_BY_SYMBOL]->(SymbolOccurrenceShadow)` when correlation is high-confidence.
- `(PublicApiSymbol)-[:BRIDGE_EXPORT_OF]->(PublicApiSymbol)` when SKIE/bridge metadata can identify Kotlin source to Swift exported symbol.

The spec deliberately does not reuse `SymbolOccurrence` as the primary record. Public API membership is a module-surface fact, while `SymbolOccurrence` is an occurrence/search fact.

For v1, "high-confidence" correlation means normalized FQN exact match only. No fuzzy, embedding, suffix-only, or basename-only matching is allowed without a later spec revision.

## Pre-Formalization Decisions Required

CTO Phase 1.1 must close these before writing an implementation plan:

1. Surface retention: latest-only per module, or versioned-per-commit snapshots from v1. This affects Neo4j volume, eviction policy, and how much substrate #31 can reuse.
2. #31 schema contract: #31 should either consume `PublicApiSymbol` directly or create separate `ContractSymbol` nodes linked back to #27. This must be decided before #27 implementation to avoid a schema migration immediately after merge.
3. Swift visibility policy: whether Swift `package` visibility is included for package-internal UW analysis or excluded from external public API v1.
4. Swift artifact source: `.swiftinterface` vs `swift-api-digester` must be selected by smoke evidence, not by preference.

## Parser Strategy

### Kotlin

Primary input: binary-compatibility-validator `.api` dumps.

Rules:

- Parse only public/protected/effectively public entries emitted by BCV.
- Preserve raw signature text before normalization.
- Normalize JVM-style nested class names and Kotlin function/property signatures into a stable FQN and signature hash.
- Treat KLib `.klib.api` as optional smoke-gated input, not required v1.
- Do not run `apiDump` inside the extractor in v1. Generation is a fixture/runbook responsibility.

### Swift

Phase 1.1 smoke must pick the v1 artifact source before implementation:

- Candidate A: `.swiftinterface` parsing from build artifacts produced with library evolution enabled.
- Candidate B: `swift-api-digester`/SwiftPM API diagnostics output if it produces stable machine-readable or parseable output on the fixture and real UW/HS Kit sample.

Rules:

- Exclude `internal`, `private`, and implementation-only declarations.
- Preserve `public`, `open`, and `package` distinctly if the selected artifact exposes them.
- Do not treat Swift `package` visibility as public external API unless the operator explicitly accepts package-scope API as in-scope.
- Record toolchain version in `PublicApiSurface.tool_version` because Swift output can change across Xcode versions.

### SKIE Overlay

SKIE handling is optional enrichment:

- If SKIE artifacts are absent, extractor records a skip metric and succeeds.
- If present, parse overlay declarations and mark corresponding Swift-side exported symbols as `is_bridge_exported=true`.
- Do not make SKIE required for non-KMP repositories.
- Do not merge #4 KMP Platform-Bridge schema into #27. #27 records exported symbols; #4 owns full expect/actual and bridge lifecycle semantics.

## Affected Files And Areas

Expected implementation areas after spec approval:

- `services/palace-mcp/src/palace_mcp/extractors/public_api_surface.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
- `services/palace-mcp/tests/extractors/unit/test_public_api_surface*.py`
- `services/palace-mcp/tests/extractors/integration/test_public_api_surface_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/public-api-surface-mini-project/`
- Optional runbook: `docs/runbooks/public-api-surface.md`

The implementation should avoid changes to Phase 1 symbol index extractors unless a correlation helper is shared and additive.

## Acceptance Criteria

1. Kotlin fixture `.api` dump ingestion creates one `PublicApiSurface` and multiple `PublicApiSymbol` nodes.
2. Swift fixture ingestion creates one `PublicApiSurface` and multiple `PublicApiSymbol` nodes from the smoke-selected artifact source.
3. Private/internal declarations in Kotlin and Swift fixtures are excluded.
4. Kotlin `internal` declarations annotated as effectively public by BCV are represented as `published_api_internal` or another explicitly tested visibility value.
5. Stable IDs and `signature_hash` values are deterministic across two identical fixture runs.
6. The extractor records artifact kind and tool version for every surface snapshot.
7. SKIE overlay absence is a successful no-op, not an extractor failure.
8. If a SKIE overlay fixture is included, at least one Swift exported symbol is marked `is_bridge_exported=true`.
9. Correlation to `SymbolOccurrenceShadow` is attempted only when a high-confidence normalized FQN match exists.
10. Integration test can query exported symbols by module name and language.
11. Integration test can query exported symbols without requiring Tantivy schema changes.
12. Failure modes use explicit `ExtractorErrorCode` values and are covered by wire-level tests where MCP boundaries are touched.

## Verification Plan

Pre-implementation smoke:

- Generate a tiny Kotlin `.api` dump from a fixture module using BCV `apiDump`.
- Generate Swift public API evidence from both `.swiftinterface` and `swift-api-digester` candidates, then choose the least fragile v1 source.
- Optional: probe a minimal SKIE/KMP sample only if local tooling is already available; otherwise mark SKIE as enrichment follow-up inside the spec.

Implementation verification:

- `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_public_api_surface*.py`
- `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_public_api_surface_integration.py`
- `cd services/palace-mcp && uv run pytest tests/integration/test_mcp_*public_api*` if MCP wire tools are added.
- `cd services/palace-mcp && uv run ruff format --check src tests`
- `cd services/palace-mcp && uv run ruff check src tests`
- `cd services/palace-mcp && uv run mypy src`

## Risks

- Swift tooling can blur source API and ABI. The smoke gate must freeze whether #27 records public source declarations, ABI-visible declarations, or both as distinct `artifact_kind` values.
- BCV is in maintenance mode and KLib ABI support is experimental. v1 should rely on JVM `.api` dumps unless KLib smoke passes.
- Public API artifacts require compilation. Broken builds mean no new snapshot; the extractor must surface this as missing artifact or generation failure, not silently produce partial graphs.
- Generated bridge symbols can create noisy surfaces. `is_generated`, `is_bridge_exported`, and `bridge_source` must be first-class fields.
- FQN correlation to Phase 1 symbol indexes may be incomplete across Swift and Kotlin naming schemes. Correlation should be best-effort with explicit confidence rules.

## Open Questions For Review

1. Should Swift `package` visibility be included as public surface for package-internal UW module analysis, or excluded from v1 external API?
2. Should #27 store only the latest surface per module, or versioned surfaces per commit from the start?
3. Should Kotlin KLib `.klib.api` support be a v1 gate or a follow-up after JVM `.api` support lands?
4. Should `PublicApiSymbol` be the shared node consumed by #31, or should #31 create separate `ContractSymbol` nodes linked back to #27?
5. Should API artifact generation scripts live under `services/palace-mcp/scripts/` or stay in fixture/runbook land for v1?
