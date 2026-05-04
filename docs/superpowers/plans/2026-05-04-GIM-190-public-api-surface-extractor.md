# GIM-190 — Public API Surface Extractor — Implementation Plan

План разбивает GIM-190 на проверяемые шаги после Phase 1.2 review. Источник истины: `docs/superpowers/specs/2026-05-04-GIM-190-public-api-surface-extractor.md`. Implementation не стартует, пока CXCodeReviewer не утвердит spec + plan.

## Scope

- In: extractor `public_api_surface`, graph model, Kotlin `.api` parser, Swift `.swiftinterface` parser, optional SKIE no-op/enrichment path, exact FQN correlation, tests, runbook.
- Out: breaking-change classification, consumer impact, automatic edits to UW build files, KLib hard gate, C/C++/Obj-C ABI extraction, Tantivy schema migration.

## Steps

### Step 1 — Plan-first review gate

**Description:** Review spec decisions, external reference basis, data model, and decomposition before implementation.
**Acceptance criteria:** CXCodeReviewer comment explicitly approves or requests changes; no implementation issue is assigned before approval.
**Suggested owner:** CXCodeReviewer.
**Affected paths:** `docs/superpowers/specs/2026-05-04-GIM-190-public-api-surface-extractor.md`, this plan.
**Dependencies:** Phase 1.1 CTO formalization complete.

### Step 2 — Fixture artifact spike and parser truth

**Description:** Create minimal committed fixture artifacts for Kotlin BCV `.api` and Swift `.swiftinterface`; optionally add `swift-api-digester` smoke notes only as comparison evidence. Do not edit production UW build files.
**Acceptance criteria:** Fixtures include public/open/protected/package/internal/private cases; committed fixture README explains how artifacts were generated; CR can review artifact semantics without running Gradle/Xcode.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/tests/extractors/fixtures/public-api-surface-mini-project/`, optional `docs/runbooks/public-api-surface.md`.
**Dependencies:** Step 1.

### Step 3 — Add graph model and schema writes

**Description:** Add `PublicApiSurface`, `PublicApiSymbol`, and `EXPORTS` / `BACKED_BY_SYMBOL` / optional `BRIDGE_EXPORT_OF` write support using existing extractor foundation patterns.
**Acceptance criteria:** Schema/model tests cover required fields, uniqueness/stable IDs, commit-aware identities, and no Tantivy schema dependency.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`, `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`, related tests.
**Dependencies:** Step 2.

### Step 4 — Implement Kotlin `.api` parser

**Description:** Parse committed BCV `.api` fixtures into normalized symbol records with deterministic FQN/signature hash and visibility mapping.
**Acceptance criteria:** Unit tests cover classes/interfaces/functions/properties/constructors/nested names; private/internal exclusions are explicit; unknown/effectively-public internals are handled without guessing.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/public_api_surface.py`, `services/palace-mcp/tests/extractors/unit/test_public_api_surface*.py`.
**Dependencies:** Step 2.

### Step 5 — Implement Swift `.swiftinterface` parser

**Description:** Parse `.swiftinterface` fixtures into normalized symbol records while preserving `public`, `open`, and `package` policy.
**Acceptance criteria:** Unit tests cover structs/classes/enums/protocols/functions/properties/initializers/typealiases/extensions; default external-public query excludes `package`; toolchain/version metadata is recorded.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/public_api_surface.py`, Swift fixture tests.
**Dependencies:** Step 2.

### Step 6 — Register extractor and graph integration

**Description:** Register `public_api_surface`, wire artifact input discovery, graph writes, exact FQN `BACKED_BY_SYMBOL` correlation, and module/language/commit query behavior using existing registry/composite patterns.
**Acceptance criteria:** Integration test creates surfaces/symbols, exports edges, and exact backing edges only when fixture FQNs match; SKIE missing path returns successful skip evidence.
**Suggested owner:** CXPythonEngineer; CXMCPEngineer only if a public MCP contract is added.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/registry.py`, extractor implementation, integration tests, optional MCP composite files.
**Dependencies:** Steps 3, 4, 5.

### Step 7 — Optional SKIE overlay enrichment

**Description:** Add optional parser/no-op path for SKIE overlay artifacts without making SKIE required for non-KMP repositories.
**Acceptance criteria:** Absence test proves no failure; presence fixture marks at least one Swift symbol `is_bridge_exported=true` only when metadata is deterministic.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** extractor implementation, fixtures, unit/integration tests.
**Dependencies:** Step 6.

### Step 8 — Runbook and operator contract

**Description:** Document artifact expectations, mount paths, generation boundaries, and common failure modes.
**Acceptance criteria:** Runbook says extractor consumes artifacts and does not edit UW build files; includes Kotlin and Swift artifact examples; names graph query smoke expected from QA.
**Suggested owner:** CXTechnicalWriter if available; otherwise CXPythonEngineer after implementation.
**Affected paths:** `docs/runbooks/public-api-surface.md`.
**Dependencies:** Steps 2, 6.

### Step 9 — Review, adversarial review, and QA

**Description:** Complete the standard phase chain with pushed branch evidence, review findings resolved, runtime smoke, graph invariant check, and merge readiness check.
**Acceptance criteria:** CXCodeReviewer approves code; CodexArchitectReviewer approves architecture; CXQAEngineer posts Phase 4.1 evidence with commit SHA, targeted tests, runtime smoke, and graph query; CXCTO runs merge-readiness reality-check before merge/close.
**Suggested owner:** CXCodeReviewer, CodexArchitectReviewer, CXQAEngineer, CXCTO.
**Affected paths:** issue comments, PR #87, CI/QA evidence.
**Dependencies:** Steps 1–8.

## Review Risks

- Swift `.swiftinterface` generation is not always available for package-internal builds; implementation must fail/skip explicitly when artifacts are absent.
- Kotlin BCV and Kotlin Gradle Plugin binary validation are in transition; parser must consume committed artifact text, not plugin internals.
- Versioned-per-commit snapshots increase graph cardinality; v1 controls this through explicit artifact ingestion only.
- Exact FQN backing edges may be sparse; sparse correlation is acceptable, fuzzy matching is not.
