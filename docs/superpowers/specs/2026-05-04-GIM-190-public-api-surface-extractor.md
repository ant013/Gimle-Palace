# GIM-190 — Public API Surface Extractor — Phase 1.1 Spec

**Status:** Phase 1.1 formalized, ready for CXCodeReviewer plan-first review.
**Date:** 2026-05-04.
**Issue:** GIM-190.
**Roadmap item:** #27 Public API Surface Extractor.
**Branch / PR:** `feature/GIM-190-public-api-surface-extractor`, PR #87.
**Base:** `develop@f2696fa04147a3976df3228451f9e771628e2e94`.
**Owner chain:** CXCTO → CXCodeReviewer → CXPythonEngineer/CXMCPEngineer → CXCodeReviewer → CodexArchitectReviewer → CXQAEngineer → CXCTO.

## Цель

Спроектировать детерминированный extractor `public_api_surface`, который сохраняет экспортируемую поверхность API модулей UW/HS Kits как графовые факты, пригодные для запросов по проекту, модулю, языку, kind, visibility, artifact source и commit.

Extractor отвечает на вопросы:

- какие типы, функции, свойства и initializer'ы экспортирует модуль на конкретном commit;
- какие элементы public API имеют backing symbol из Phase 1 symbol indexes;
- какие Swift-side элементы являются bridge/export overlay для Kotlin/KMP;
- какие поверхности может потреблять будущий Cross-Module Contract Extractor (#31).

Это не breaking-change extractor. Roadmap #31 отвечает за diff между версиями, классификацию breaking changes и consumer impact. GIM-190 создает нормализованный источник public-surface фактов.

## Закрытые Phase 1.1 решения

1. **Retention:** v1 хранит versioned-per-commit snapshots. `PublicApiSurface.commit_sha` обязателен, а "latest" является query/view policy, не отдельной моделью хранения. Причина: #31 сможет переиспользовать снимки без немедленной миграции схемы; объем ограничивается тем, что extractor ingest'ит только явно переданные artifacts.
2. **Contract with #31:** #31 должен потреблять `PublicApiSymbol` напрямую и создавать собственные delta/contract-result сущности поверх него. Отдельный `ContractSymbol` в #31 запрещен для v1, если он дублирует тот же symbol identity.
3. **Swift `package` visibility:** `package` сохраняется как отдельное значение `visibility`, если artifact его экспонирует, но не считается external public API по умолчанию. Query/API должны требовать явный `include_package=true` или отдельный internal-surface mode.
4. **Swift artifact source:** v1 primary source — compiler-emitted `.swiftinterface` when available. `swift-api-digester` остается smoke/diagnostic fallback and future #31 diff aid, но не primary source для GIM-190 v1. Причина: GIM-190 хранит surface snapshot, а не diff; Swift.org documents `.swiftinterface` as emitted module interface under library-evolution/module-stability builds, while `swift-api-digester` is framed as a tool for dumping/comparing module API and diagnosing source-breaking changes.

## Verified Reference Basis

Проверено 2026-05-04 перед формализацией:

- Kotlin BCV: JetBrains/Kotlin docs describe `.api` dumps and `apiDump` / `apiCheck`; Kotlin docs also state that Kotlin Gradle Plugin 2.2.0 adds binary compatibility validation with the same semantics. Source: <https://github.com/Kotlin/binary-compatibility-validator>, <https://kotlinlang.org/docs/api-guidelines-backward-compatibility.html>.
- Swift `.swiftinterface`: Swift.org library evolution docs state that library evolution/module interface emission produces `.swiftinterface` files and separates source-public/ABI-public concepts. Source: <https://www.swift.org/blog/library-evolution/>.
- Swift API digester: Swift Forums records the tool as dumping module content and comparing two JSON dumps for source-breaking API changes. Source: <https://forums.swift.org/t/using-swift-api-digester/22956>.
- SKIE: Touchlab documents SKIE as enhancing Swift API published from Kotlin and generating Swift-friendly bridge surface. Source: <https://skie.touchlab.co/intro>.

No implementation spec line depends on an unverified Python import or library method call. Any future implementation plan that names concrete external APIs must add a dated spike under `docs/research/` or cite an existing `reference_<lib>_api_truth.md` memory before CR approval.

## Assumptions

- Phase 1 symbol indexes are the source of truth for source occurrences and locations; GIM-190 stores public-surface membership.
- v1 ingests pre-generated artifacts. It does not mutate production Gradle, SwiftPM, or Xcode project configuration to generate dumps.
- Kotlin/JVM `.api` dumps and Swift `.swiftinterface` artifacts are v1 gates.
- KLib and SKIE are designed as optional enrichment because KMP adoption and local tool availability vary by module.
- C/C++/Objective-C ABI extraction is out of v1. GIM-184 provides native source symbols, not stable binary ABI surface.
- Public API generation can fail because upstream builds fail; missing artifacts must be explicit extractor failures or skips, not silent partial success.

## Scope

### In Scope

- New extractor identity: `public_api_surface`.
- `PublicApiSurface` and `PublicApiSymbol` graph model.
- Kotlin ingestion from pre-generated BCV `.api` files.
- Swift ingestion from pre-generated `.swiftinterface` files.
- Optional `swift-api-digester` fixture smoke to validate fallback feasibility, without making it the v1 primary source.
- Optional SKIE overlay parsing when artifacts are present.
- Exact-match correlation from `PublicApiSymbol` to `SymbolOccurrenceShadow`.
- Unit and integration tests for parsing, visibility filtering, stable IDs, signature hashing, graph writes, and query paths.
- Runbook text for generating or mounting public API artifacts outside extractor runtime.

### Out Of Scope

- Breaking-change classification and semantic version advice (#31).
- Consumer impact / cross-module import analysis (#31/#45).
- Documentation coverage (#37).
- Coverage-gap scoring (#28).
- Dead public symbol reachability (#33).
- Automatic installation of Gradle plugins or edits to UW build files.
- KLib ABI support as a hard v1 gate.
- Objective-C, Objective-C++, C, and C++ ABI export extraction.
- Tantivy schema changes.

## Data Model

### `PublicApiSurface`

- `id`: stable hash of `project`, `module_name`, `language`, `commit_sha`, `artifact_path`, `artifact_kind`, and `tool_name`.
- `project`
- `module_name`
- `language`: `kotlin`, `swift`, later `unknown` only for forward-compatible ingestion.
- `commit_sha`
- `artifact_path`
- `artifact_kind`: `kotlin_bcv_api`, `swiftinterface`, `swift_api_digester`, `skie_overlay`.
- `tool_name`
- `tool_version`
- `generated_at`: nullable if artifact lacks timestamp.
- `schema_version`: initial value `1`.

### `PublicApiSymbol`

- `id`: stable hash of `project`, `module_name`, `language`, normalized `fqn`, `signature_hash`, `artifact_kind`, and `commit_sha`.
- `project`
- `module_name`
- `language`
- `commit_sha`
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
- `symbol_qualified_name`: nullable exact-match correlation key into Phase 1 indexes.
- `schema_version`: initial value `1`.

### Edges

- `(PublicApiSurface)-[:EXPORTS]->(PublicApiSymbol)`.
- `(PublicApiSymbol)-[:BACKED_BY_SYMBOL]->(SymbolOccurrenceShadow)` only for exact normalized FQN match.
- `(PublicApiSymbol)-[:BRIDGE_EXPORT_OF]->(PublicApiSymbol)` only when bridge metadata identifies the source symbol without fuzzy matching.

`PublicApiSymbol` must not replace `SymbolOccurrenceShadow`; these entities answer different questions. Surface membership is module-level API state. Symbol occurrence is code-search/source-index state.

## Parser Policy

### Kotlin

- Input: pre-generated BCV `.api` file.
- Parse only entries emitted by the artifact as public/protected/effectively public.
- Preserve raw signature text before normalization.
- Normalize nested names, function/property signatures, constructors, and companion/static forms into deterministic FQN + signature hash.
- Represent effectively public Kotlin internals as `published_api_internal` only when the artifact exposes that distinction; otherwise `unknown` plus raw signature evidence is preferable to guessing.
- KLib `.klib.api` is follow-up unless a dated spike proves stable parser semantics before implementation.

### Swift

- Input: pre-generated `.swiftinterface` file.
- Preserve `public`, `open`, and `package` distinctly if present.
- Exclude `internal`, `fileprivate`, `private`, and implementation-only declarations.
- Store Swift toolchain version in `PublicApiSurface.tool_version`.
- Treat `.swiftinterface` as source/interface snapshot, not ABI proof. ABI-specific questions require a later artifact kind or #31 diff logic.
- `swift-api-digester` can be used by tests/spikes to compare parser completeness, but v1 graph writes must not require it.

### SKIE Overlay

- Absence of SKIE artifacts is successful skip with explicit metric/evidence.
- Presence of SKIE artifacts may mark Swift-side symbols as `is_bridge_exported=true` and `bridge_source=skie`.
- GIM-190 does not own full KMP bridge lifecycle or expect/actual semantics; roadmap #4 owns that deeper model.

## Affected Areas After Approval

Expected implementation paths:

- `services/palace-mcp/src/palace_mcp/extractors/public_api_surface.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
- `services/palace-mcp/tests/extractors/unit/test_public_api_surface*.py`
- `services/palace-mcp/tests/extractors/integration/test_public_api_surface_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/public-api-surface-mini-project/`
- `docs/runbooks/public-api-surface.md`

Implementation should avoid changes to existing Phase 1 symbol-index extractors unless a shared helper is strictly additive and covered by regression tests.

## Acceptance Criteria

1. Kotlin fixture `.api` ingestion creates one `PublicApiSurface` and expected `PublicApiSymbol` nodes.
2. Swift fixture `.swiftinterface` ingestion creates one `PublicApiSurface` and expected `PublicApiSymbol` nodes.
3. Private/internal declarations from fixtures are excluded.
4. Swift `package` declarations are preserved as `visibility=package` and excluded from default external-public query mode.
5. Stable IDs and `signature_hash` are deterministic across two identical fixture runs.
6. Every surface records `artifact_kind`, `tool_name`, `tool_version`, `commit_sha`, and `schema_version`.
7. SKIE absence is a successful skip, not an extractor failure.
8. If a SKIE fixture is added, at least one exported Swift symbol is marked `is_bridge_exported=true`.
9. Correlation to `SymbolOccurrenceShadow` uses exact normalized FQN match only.
10. Integration test queries exported symbols by module, language, commit, and visibility.
11. No Tantivy schema migration is required.
12. Failure modes use explicit extractor error codes where existing extractor framework supports them.

## Verification Plan

Implementation agents must provide:

- Unit tests for Kotlin parser, Swift parser, stable IDs, visibility filtering, and signature hashing.
- Integration test proving graph nodes/edges and query path over Neo4j/testcontainer or the existing extractor integration harness.
- Real fixture artifacts committed under test fixtures; generation scripts or notes must not modify production UW/HS build files.
- `uv run ruff check`, `uv run mypy src/`, and targeted `uv run pytest` evidence from the implementation workspace.
- QA Phase 4.1 evidence with runtime smoke, graph invariant query, and MCP/tool-level query if a public MCP surface is added.

CTO Phase 1.1 verification is docs-only: branch rename, docs diff, PR metadata, and Markdown whitespace check. Runtime tests are explicitly out of scope for CTO formalization.

## Risks And Controls

- **Swift artifact fragility:** `.swiftinterface` requires library evolution/module-interface emission. Control: v1 requires pre-generated artifacts and records toolchain version.
- **BCV maintenance mode / Kotlin Gradle Plugin transition:** v1 consumes artifact format rather than binding to plugin internals. Control: implementation parser tests use committed fixture artifacts.
- **Graph volume:** versioned-per-commit can grow. Control: extractor only ingests explicitly supplied artifacts; retention/eviction policy can be added after empirical volume data.
- **FQN mismatch:** Swift and Kotlin naming schemes may not align with Phase 1 indexes. Control: exact-match only, nullable backing edge, no fuzzy correlation in v1.
- **Bridge noise:** generated bridge API can swamp native API. Control: `is_generated`, `is_bridge_exported`, and `bridge_source` are first-class fields.

## Handoff Requirements

Before implementation starts:

1. CXCodeReviewer must approve this spec and the plan at `docs/superpowers/plans/2026-05-04-GIM-190-public-api-surface-extractor.md`.
2. If CR requests changes on external tool assumptions, add a dated spike or remove the unsupported assumption before implementation.
3. After CR approval, implementation is assigned to CXPythonEngineer unless CXMCPEngineer owns a narrow MCP contract change.
4. No implementation sub-issues are created from Phase 1.1 until plan-first review passes.
