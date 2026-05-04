# GIM-192 - Cross-Module Contract Extractor - Phase 1.1 Spec

**Статус:** Phase 1.1 formalized, ready for CXCodeReviewer plan-first review.
**Date:** 2026-05-04.
**Issue:** GIM-192.
**Roadmap item:** #31 Cross-Module Contract Extractor.
**Branch:** `feature/GIM-192-cross-module-contract`.
**Base:** `develop@2a96786e9d9d07e02dd6283d3193f8b4302b77b6`.
**Plan:** `docs/superpowers/plans/2026-05-04-GIM-192-cross-module-contract-extractor.md`.
**Predecessor:** GIM-190 Public API Surface Extractor is merged and deployed on `develop@2a96786e9d9d07e02dd6283d3193f8b4302b77b6`.

## Goal

Добавить extractor `cross_module_contract`, который строит факты о том, какие modules consume public API других modules на конкретном commit.

Extractor отвечает на вопросы:

- какие exported symbols одного module реально потребляются другим module;
- какие module-to-module contract snapshots существуют на commit;
- какой blast radius будет у удаления или изменения public symbol, если future diff stage сравнит два commits;
- какие gaps остаются из-за отсутствующего exact backing key, без fuzzy matching и без догадок.

GIM-192 не переизобретает Public API Surface. Источник exported surface - GIM-190 `PublicApiSurface` / `PublicApiSymbol`.

## Closed Phase 1.1 Decisions

1. **Storage identity:** v1 хранит `versioned-per-commit` snapshots. `commit_sha` обязателен на каждом new contract node/edge. "Latest" является query/view policy, не отдельной моделью хранения.
2. **No duplicate symbol schema:** v1 не добавляет `ContractSymbol`. Contract facts ссылаются на существующий `PublicApiSymbol` из GIM-190.
3. **Default scope:** v1 строит cross-module consumption contracts. Breaking-change classification ограничена минимальным delta substrate между двумя explicitly selected commits и не включает semver advice, compatibility scoring или release policy.
4. **Matching policy:** v1 использует только exact matching. Если `PublicApiSymbol.symbol_qualified_name` отсутствует или не совпадает с indexed occurrence key, symbol остается surface-only и не получает consumer edge.
5. **Package visibility:** default external contract excludes Swift `visibility=package`. Internal/package mode может быть отдельным параметром/query path, но не должен смешиваться с external contract по умолчанию.
6. **Roadmap:** `docs/roadmap.md` уже держит #31 downstream of #27 (`deps #27`). Открытый PR #90 отдельно обновляет roadmap lane after GIM-190, поэтому этот branch не трогает roadmap, чтобы не конфликтовать с docs-only roadmap PR.

## Verified Reference Basis

Проверено 2026-05-04 перед формализацией:

- GIM-190 spec and implementation define `PublicApiSurface`, `PublicApiSymbol`, `EXPORTS`, `BACKED_BY_SYMBOL`, `commit_sha`, `module_name`, `symbol_qualified_name`, and the rule that #31 must consume `PublicApiSymbol` directly.
- Kotlin Binary Compatibility Validator documents `.api` dumps plus `apiDump` / `apiCheck`; GIM-190 already consumes `.api` artifacts rather than plugin internals. Source: <https://github.com/Kotlin/binary-compatibility-validator>.
- Swift module interface / API diffing is treated as artifact-level evidence, not as a runtime dependency for this extractor. GIM-190 uses `.swiftinterface` as primary Swift surface input; `swift-api-digester` remains diagnostic/future diff aid.
- oasdiff is a rule-catalog inspiration for later compatibility classification only; v1 does not bind to oasdiff APIs or OpenAPI-specific rules. Source: <https://www.oasdiff.com/docs/breaking-changes>.
- Adyen's Swift API diffing write-up is useful prior art for reviewing Swift public API changes, but GIM-192 v1 does not shell out to `adyen-swift-public-api-diff`. Source: <https://www.adyen.com/knowledge-hub/swift-api-diff>.

No implementation spec line depends on an unverified Python import or external library method. Any future revision that names concrete external APIs must add a dated spike under `docs/research/` or cite a valid reference memory before CR approval.

## Assumptions

- GIM-190 artifacts are present for the target project before `cross_module_contract` runs.
- Phase 1 symbol indexes still provide occurrence-level evidence. GIM-192 stores contract membership and consumer evidence, not full source occurrences.
- Module identity comes first from `PublicApiSurface.module_name` for producer modules and from existing module/source ownership metadata for consumer files. If consumer module cannot be resolved exactly, the occurrence is skipped with explicit skip metrics.
- v1 runs on explicitly ingested commits. It does not crawl git history or choose commit pairs by itself.
- GIM-191 / #5 Dependency Surface may later enrich producer/consumer candidate pruning, but GIM-192 v1 must not require that slice.
- Generated bridge symbols are included only when they are already represented by GIM-190 fields and exact keys; KMP bridge semantics remain owned by roadmap #4.

## Scope

### In Scope

- New extractor identity: `cross_module_contract`.
- New graph model for module-to-module contract snapshots and optional minimal deltas.
- Consumption edges from contract snapshots to existing `PublicApiSymbol`.
- Exact-match correlation from source occurrences / `SymbolOccurrenceShadow` to `PublicApiSymbol.symbol_qualified_name`.
- Same-module exclusion: producer and consumer module must differ.
- Commit-aware matching: producer surface, public symbol, source occurrence, and contract snapshot must share the same `commit_sha`.
- Default filtering that excludes `visibility=package` unless internal/package mode is explicitly enabled.
- Unit and integration tests for exact matching, skip reasons, graph writes, same-module exclusion, package visibility policy, and deterministic IDs.
- Runtime smoke that runs after GIM-190 fixture ingestion and proves graph invariants with Neo4j queries.

### Out Of Scope

- Duplicating `PublicApiSymbol` as `ContractSymbol`.
- Fuzzy FQN matching, edit-distance matching, demangling guesses, or "best effort" cross-language symbol merging.
- Full breaking-change taxonomy, semver advice, release-note generation, or CI policy enforcement.
- Automatic artifact generation for Kotlin/Swift public API surfaces.
- Git-history harvesting or automatic old/new commit selection.
- Dependency resolver changes, package-manager graph ingestion, or manifest parsing from roadmap #5.
- Tantivy schema migration.
- Production deploy automation changes.

## Data Model

### `ModuleContractSnapshot`

One producer/consumer module pair at one commit.

- `id`: stable hash of `group_id`, `project`, `consumer_module_name`, `producer_module_name`, `language`, `commit_sha`, `include_package`, and `schema_version`.
- `group_id`
- `project`
- `consumer_module_name`
- `producer_module_name`
- `language`
- `commit_sha`
- `include_package`
- `producer_surface_id`
- `symbol_count`
- `use_count`
- `file_count`
- `skipped_symbol_count`
- `schema_version`

### `ModuleContractDelta`

Minimal comparison record for two explicitly supplied commits. This is substrate for later breaking-change work, not a full compatibility classifier.

- `id`: stable hash of `snapshot_from_id`, `snapshot_to_id`, and `schema_version`.
- `group_id`
- `project`
- `consumer_module_name`
- `producer_module_name`
- `language`
- `from_commit_sha`
- `to_commit_sha`
- `removed_consumed_symbol_count`
- `signature_changed_consumed_symbol_count`
- `added_consumed_symbol_count`
- `affected_use_count`
- `classification_scope`: initial value `minimal_symbol_delta`
- `schema_version`

### Edges

- `(ModuleContractSnapshot)-[:CONTRACT_PRODUCER_SURFACE]->(PublicApiSurface)`.
- `(ModuleContractSnapshot)-[:CONSUMES_PUBLIC_SYMBOL]->(PublicApiSymbol)` with properties:
  - `group_id`
  - `commit_sha`
  - `match_key`: `symbol_qualified_name`
  - `use_count`
  - `file_count`
  - `first_seen_path`
  - `evidence_paths_sample`
  - `schema_version`
- `(ModuleContractDelta)-[:DELTA_FROM]->(ModuleContractSnapshot)`.
- `(ModuleContractDelta)-[:DELTA_TO]->(ModuleContractSnapshot)`.
- `(ModuleContractDelta)-[:AFFECTS_PUBLIC_SYMBOL]->(PublicApiSymbol)` only for exact old/new symbol identities already represented by GIM-190.

Do not create `(:ContractSymbol)` in v1.

## Matching Rules

Candidate producer symbols:

1. Select `PublicApiSurface` rows for target `project`, `language`, `commit_sha`, and producer `module_name`.
2. Traverse `(:PublicApiSurface)-[:EXPORTS]->(:PublicApiSymbol)`.
3. Exclude `visibility=package` unless `include_package=true`.
4. Require non-empty `PublicApiSymbol.symbol_qualified_name` for consumer matching.

Candidate consumer evidence:

1. Use indexed source occurrences / shadows with the same `group_id`, `project`, `language`, and `commit_sha`.
2. Keep reference/use occurrences only; definitions of the producer symbol do not count as consumption.
3. Resolve `consumer_module_name` from exact module/file ownership metadata. If not available, skip with `consumer_module_unresolved`.
4. Exclude same-module matches where `consumer_module_name == producer_module_name`.

Exact match:

```text
PublicApiSymbol.symbol_qualified_name == SymbolOccurrenceShadow.symbol_qualified_name
```

No fallback is allowed in v1:

- no substring FQN matching;
- no case-insensitive matching;
- no Kotlin/Swift cross-language normalization guesses;
- no matching on `display_name` alone;
- no matching on `signature_hash` without `symbol_qualified_name`.

## Version And Retention Policy

GIM-192 inherits GIM-190's versioned-per-commit model.

- Store snapshots for every commit explicitly ingested.
- Store deltas only when an explicit old/new commit pair is requested by implementation or QA flow.
- Treat "latest contract" as a query over max accepted `commit_sha` / ingest time, not as a separate mutable node.
- No eviction policy in v1. If graph volume becomes material, add a separate retention slice based on empirical node/edge counts from Phase 4.1 evidence.

## Affected Areas After Approval

Expected implementation paths:

- `services/palace-mcp/src/palace_mcp/extractors/cross_module_contract.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
- `services/palace-mcp/tests/extractors/unit/test_cross_module_contract*.py`
- `services/palace-mcp/tests/extractors/integration/test_cross_module_contract_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/cross-module-contract-mini-project/`
- `docs/runbooks/cross-module-contract.md` if operator workflow text is added in this slice.

Implementation should avoid edits to `public_api_surface.py` unless a small shared helper is strictly additive and regression-tested. Any change to existing GIM-190 field semantics must include a fresh `rg`/grep call-site audit in the implementation PR.

## Acceptance Criteria

1. `cross_module_contract` is registered and runnable through the existing extractor runner.
2. Fixture with at least two modules creates one or more `ModuleContractSnapshot` nodes.
3. Snapshot IDs are deterministic across two identical fixture runs.
4. `CONSUMES_PUBLIC_SYMBOL` edges point to existing `PublicApiSymbol` nodes, not duplicated contract symbols.
5. Same-module references are excluded.
6. `visibility=package` symbols are excluded by default and included only when explicitly requested.
7. Symbols with null or unmatched `symbol_qualified_name` are skipped with explicit metrics.
8. Graph writes are commit-aware; no edge crosses commit boundaries.
9. Minimal `ModuleContractDelta` compares explicitly selected commits only and reports symbol-level add/remove/signature-change counts without semver advice.
10. Integration tests prove graph invariants over Neo4j/testcontainer or existing extractor integration harness.
11. QA Phase 4.1 posts runtime evidence with a real MCP/tool invocation or extractor runner smoke plus direct Neo4j invariant queries.

## Verification Plan

Implementation agents must provide:

- Unit tests for exact matching, skip reasons, package visibility, deterministic IDs, same-module exclusion, and delta counts.
- Integration test that first loads GIM-190 public API fixture data, then runs `cross_module_contract`.
- Direct graph invariant queries:
  - no `ContractSymbol` nodes created;
  - every `CONSUMES_PUBLIC_SYMBOL` target is a `PublicApiSymbol`;
  - snapshot `commit_sha` equals all consumed symbol `commit_sha`;
  - no same-module snapshots exist;
  - default run has zero `visibility=package` consumed symbols.
- Targeted validation commands from `services/palace-mcp`:
  - `uv run pytest tests/extractors/unit/test_cross_module_contract*.py -v`
  - `uv run pytest tests/extractors/integration/test_cross_module_contract_integration.py -v`
  - `uv run ruff check src/palace_mcp/extractors tests/extractors`
  - `uv run mypy src/`

CTO Phase 1.1 verification is docs-only: branch ancestry, docs diff, PR metadata, and `git diff --check`. Runtime tests are explicitly out of scope for CTO formalization.

## Risks And Controls

- **Sparse exact keys:** Some `PublicApiSymbol` rows may lack `symbol_qualified_name`. Control: skip explicitly; do not fuzzy-match.
- **Graph volume:** Per-commit producer/consumer snapshots can grow as modules increase. Control: v1 stores only explicit ingests and records counts for later retention decisions.
- **Package/internal leakage:** Swift `package` visibility can look public in artifacts. Control: exclude by default and test internal mode separately.
- **Cross-language bridge ambiguity:** KMP bridge symbols may have multiple representations. Control: use GIM-190 bridge metadata only when exact; defer deeper bridge semantics to #4.
- **Dependency-surface overlap:** #5/GIM-191 may later offer better module dependency pruning. Control: keep GIM-192 independent and additive.

## Open Questions

1. Should internal/package mode ship in v1 as an extractor parameter, or remain query-only follow-up after external mode is proven?
2. Should `ModuleContractDelta` be implemented in the first engineering slice, or deferred until snapshot graph evidence from Phase 4.1 gives volume and usefulness data?
3. Should a later #5 integration prune candidate producer modules before exact matching, or is exact occurrence correlation fast enough for the real UW-iOS bundle?

## Handoff Requirements

Before implementation starts:

1. CXCodeReviewer must approve this spec and the plan at `docs/superpowers/plans/2026-05-04-GIM-192-cross-module-contract-extractor.md`.
2. If CR requests changes on matching semantics or external tool assumptions, revise this spec before creating implementation subtasks.
3. After CR approval, implementation is assigned to CXPythonEngineer unless CXMCPEngineer owns a narrow MCP/query contract change.
4. No implementation sub-issues are created from Phase 1.1 until plan-first review passes and operator confirms the phase chain.
