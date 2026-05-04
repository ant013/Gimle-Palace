# GIM-192 - Cross-Module Contract Extractor - Implementation Plan

План разбивает GIM-192 на проверяемые шаги после Phase 1.2 review. Источник истины: `docs/superpowers/specs/2026-05-04-GIM-192-cross-module-contract-extractor.md`. Implementation не стартует, пока CXCodeReviewer не утвердит spec + plan и operator не подтвердит phase chain.

## Scope

- In: extractor `cross_module_contract`, `ModuleContractSnapshot`, optional minimal `ModuleContractDelta`, exact `PublicApiSymbol` consumption edges, fixture, tests, runtime smoke.
- Out: duplicate `ContractSymbol`, fuzzy matching, full breaking-change taxonomy, semver advice, automatic API artifact generation, git-history harvesting, dependency resolver changes, Tantivy schema migration.

## Phase Steps

### Step 1 - Plan-first review gate

**Description:** Review GIM-192 spec decisions, exact matching policy, version identity, graph model, and downstream dependency on GIM-190.
**Acceptance criteria:** CXCodeReviewer explicitly approves or requests changes; implementation is not assigned before approval; reviewer confirms v1 does not duplicate `PublicApiSymbol`.
**Suggested owner:** CXCodeReviewer.
**Affected paths:** `docs/superpowers/specs/2026-05-04-GIM-192-cross-module-contract-extractor.md`, this plan.
**Dependencies:** Phase 1.1 CTO formalization complete.

### Step 2 - Fixture and graph truth

**Description:** Create a minimal committed fixture with at least two modules, GIM-190-style public API artifacts, and source/index evidence showing one module consuming another module's exported symbol.
**Acceptance criteria:** Fixture includes producer module, consumer module, same-module reference, unmatched public symbol, package/internal symbol, and two commit snapshots if delta remains in v1; fixture notes explain artifact/source truth without editing production UW build files.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/tests/extractors/fixtures/cross-module-contract-mini-project/`, fixture README/REGEN notes.
**Dependencies:** Step 1.

### Step 3 - Add contract models and schema

**Description:** Add `ModuleContractSnapshot`, optional `ModuleContractDelta`, constraints/indexes, and graph write helpers using existing extractor foundation patterns.
**Acceptance criteria:** Model/schema tests cover required fields, stable IDs, commit-aware identity, uniqueness, and absence of any new `ContractSymbol` model.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`, `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`, related unit tests.
**Dependencies:** Step 2.

### Step 4 - Implement exact matching engine

**Description:** Match `PublicApiSymbol.symbol_qualified_name` to source occurrence/shadow `symbol_qualified_name` only when project, language, group, commit, and module boundaries align.
**Acceptance criteria:** Unit tests prove exact match success, null-key skip, unmatched-key skip, same-module exclusion, reference-only consumption, default package visibility exclusion, and no display-name/signature-only fallback.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/cross_module_contract.py`, `services/palace-mcp/tests/extractors/unit/test_cross_module_contract*.py`.
**Dependencies:** Steps 2-3.

### Step 5 - Register extractor and graph integration

**Description:** Register `cross_module_contract`, discover GIM-190 surfaces for the target commit, create snapshots, and write `CONSUMES_PUBLIC_SYMBOL` edges to existing `PublicApiSymbol` nodes.
**Acceptance criteria:** Integration test first runs/loads `public_api_surface` fixture data, then runs `cross_module_contract`; graph queries prove consumed symbols are `PublicApiSymbol`, snapshot commits match symbol commits, and no same-module snapshot is written.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/registry.py`, extractor implementation, integration tests.
**Dependencies:** Step 4.

### Step 6 - Minimal delta substrate decision

**Description:** Either implement the spec's minimal explicit old/new `ModuleContractDelta` or document deferral before Phase 3 review.
**Acceptance criteria:** If implemented, tests cover removed consumed symbol, signature hash change, added consumed symbol, and affected use count without semver advice. If deferred, spec/plan are revised before CR approval of implementation scope.
**Suggested owner:** CXPythonEngineer with CXCTO decision if deferring.
**Affected paths:** extractor implementation, delta unit/integration tests, this plan/spec if scope changes.
**Dependencies:** Step 5.

### Step 7 - Optional query or runbook surface

**Description:** Add only the smallest operator-facing documentation or query surface needed to inspect contract snapshots. Avoid broad MCP API expansion unless the implementation proves it is required.
**Acceptance criteria:** If no MCP surface is added, runbook or test notes include direct Neo4j smoke queries. If MCP surface is added, response schema has targeted tests and CXMCPEngineer owns/reviews the contract.
**Suggested owner:** CXPythonEngineer for docs/query notes; CXMCPEngineer only for MCP contract changes; CXTechnicalWriter if hired for final runbook polish.
**Affected paths:** optional `docs/runbooks/cross-module-contract.md`, optional MCP/query files and tests.
**Dependencies:** Steps 5-6.

### Step 8 - Phase 3.1 mechanical review

**Description:** Review pushed implementation for scope adherence, correctness, tests, and GIM-190 contract preservation.
**Acceptance criteria:** CXCodeReviewer approves code or requests changes; reviewer pastes changed-file list and confirms every code/test path is declared in this plan; reviewer verifies no duplicate `ContractSymbol` and no fuzzy matching fallback.
**Suggested owner:** CXCodeReviewer.
**Affected paths:** PR diff and issue evidence.
**Dependencies:** Phase 2 implementation pushed.

### Step 9 - Phase 3.2 adversarial architecture review

**Description:** Challenge graph cardinality, exact matching semantics, commit boundary guarantees, and optional delta scope before QA.
**Acceptance criteria:** CodexArchitectReviewer approves architecture or requests changes; review explicitly covers versioned-per-commit storage, latest-as-query policy, package visibility default, and no cross-branch carry-over.
**Suggested owner:** CodexArchitectReviewer.
**Affected paths:** PR diff, spec, plan, evidence comments.
**Dependencies:** Step 8.

### Step 10 - Phase 4.1 QA live smoke

**Description:** Run targeted tests and a real runtime smoke that exercises GIM-190 public API facts plus GIM-192 contract extraction.
**Acceptance criteria:** CXQAEngineer evidence includes tested commit SHA, targeted pytest output, docker/runtime health, real extractor or MCP invocation, direct Neo4j invariant queries, and checkout restoration. Required invariants: zero `ContractSymbol` nodes, all consumed targets are `PublicApiSymbol`, no commit-crossing edges, no same-module snapshots, and default external mode excludes `visibility=package`.
**Suggested owner:** CXQAEngineer.
**Affected paths:** Runtime evidence comment.
**Dependencies:** Step 9.

### Step 11 - Phase 4.2 merge readiness and close

**Description:** Merge only after review and QA gates pass.
**Acceptance criteria:** CXCTO runs mandatory `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid` before claiming any merge blocker; merges into `develop` only when clean; verifies Phase 4.1 evidence is authored by CXQAEngineer; closes GIM-192 only after merge/deploy evidence.
**Suggested owner:** CXCTO.
**Affected paths:** PR into `develop`, issue thread.
**Dependencies:** Step 10.

## Concrete Smoke Gates

### Gate A - Snapshot graph

Pass:

- At least one `ModuleContractSnapshot` is created for consumer module A consuming producer module B.
- Snapshot `commit_sha` equals producer `PublicApiSurface.commit_sha` and consumed `PublicApiSymbol.commit_sha`.
- Same-module references do not create snapshots.

Fail:

- Any snapshot spans multiple commits or same producer/consumer module.

### Gate B - Symbol reuse

Pass:

- `MATCH (n:ContractSymbol) RETURN count(n)` returns `0`.
- Every `CONSUMES_PUBLIC_SYMBOL` target has label `PublicApiSymbol`.
- Edges use `match_key='symbol_qualified_name'`.

Fail:

- Implementation creates a duplicate symbol node type or matches by display name/signature alone.

### Gate C - Visibility policy

Pass:

- Default run excludes Swift `visibility=package`.
- Explicit internal/package mode, if implemented, is separately tested and does not change default external output.

Fail:

- Package/internal symbols appear in default external contract.

### Gate D - Minimal delta, if in v1

Pass:

- Delta only compares explicitly selected old/new commits.
- Counts are limited to removed consumed symbols, signature-hash changes, added consumed symbols, and affected uses.
- No semver/release policy advice is emitted.

Fail:

- Delta chooses commit history automatically or claims full breaking-change classification.

## Verification Commands

Targeted tests after implementation:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_cross_module_contract*.py -v
uv run pytest tests/extractors/integration/test_cross_module_contract_integration.py -v
```

Pre-review implementation gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src/
uv run pytest tests/extractors/unit/test_cross_module_contract*.py -v
uv run pytest tests/extractors/integration/test_cross_module_contract_integration.py -v
```

QA direct graph invariants should include:

```cypher
MATCH (n:ContractSymbol) RETURN count(n) AS duplicate_contract_symbols;

MATCH (:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(s)
WHERE NOT s:PublicApiSymbol
RETURN count(r) AS invalid_targets;

MATCH (snap:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(sym:PublicApiSymbol)
WHERE snap.commit_sha <> sym.commit_sha
RETURN count(r) AS cross_commit_edges;

MATCH (snap:ModuleContractSnapshot)
WHERE snap.consumer_module_name = snap.producer_module_name
RETURN count(snap) AS same_module_snapshots;
```

## Review Risks

- Exact matching may produce sparse output until GIM-190 backing keys are mature; sparse output is acceptable and must be visible through skip metrics.
- Minimal delta scope can creep into full breaking-change classification; reviewers should reject semver advice or non-explicit commit selection in GIM-192 v1.
- Package/internal visibility may leak into default output; tests and QA graph queries must guard this.
- GIM-191 / #5 Dependency Surface may overlap with module candidate pruning; GIM-192 must stay additive and not depend on unmerged dependency-surface work.
