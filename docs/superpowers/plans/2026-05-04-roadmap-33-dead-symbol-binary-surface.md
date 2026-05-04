---
slug: dead-symbol-binary-surface
issue: roadmap-33
spec: docs/superpowers/specs/2026-05-04-roadmap-33-dead-symbol-binary-surface.md
date: 2026-05-04
branch: feature/roadmap-33-dead-symbol-binary-surface
---

# Roadmap #33 - Dead Symbol & Binary Surface Extractor - Implementation Plan

Docs-only Phase 1.1 plan for `dead_symbol_binary_surface`. Do not implement
extractor code until this spec/plan is reviewed and a Paperclip issue is
assigned.

## Phase Chain

| Phase | Owner | Output |
|---|---|---|
| 1.1 Formalization | CTO / operator | This spec + plan branch |
| 1.2 Plan review | CXCodeReviewer | Approve/request changes before implementation |
| 2 Implementation | CXPythonEngineer | TDD implementation on a real GIM branch |
| 3.1 Mechanical review | CXCodeReviewer | Correctness, scope, tests |
| 3.2 Architecture review | CodexArchitectReviewer | False-positive model and graph semantics |
| 4.1 QA smoke | CXQAEngineer | Docker/review-profile evidence |
| 5 Merge | Operator / allowed merger | Merge after QA evidence and branch checks |

## File Structure

| Area | Files | Status |
|---|---|---|
| Extractor package | `extractors/dead_symbol_binary_surface/` | NEW |
| Models | `extractors/dead_symbol_binary_surface/models.py` | NEW |
| Periphery parser | `extractors/dead_symbol_binary_surface/parsers/periphery.py` | NEW |
| Reaper parser or skip model | `extractors/dead_symbol_binary_surface/parsers/reaper.py` | NEW or DEFER |
| Correlation | `extractors/dead_symbol_binary_surface/correlation.py` | NEW |
| Neo4j writer | `extractors/dead_symbol_binary_surface/neo4j_writer.py` | NEW |
| Extractor entry | `extractors/dead_symbol_binary_surface/extractor.py` | NEW |
| Schema | `extractors/foundation/schema.py` | EXTEND |
| Registry | `extractors/registry.py` | EXTEND |
| Fixtures | `tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/` | NEW |
| Unit tests | `tests/extractors/unit/test_dead_symbol_binary_surface*.py` | NEW |
| Integration test | `tests/extractors/integration/test_dead_symbol_binary_surface_integration.py` | NEW |
| Runbook | `docs/runbooks/dead-symbol-binary-surface.md` | NEW |

No public MCP/router/API files are in v1 scope.

## Task 0 - Tool Output Spike

### Goal

Freeze the exact input shape before writing parser code.

### Work

- Generate or commit a small Periphery output fixture for the Swift mini project.
- Prefer machine-readable output. If Periphery output is text-only in the local
  environment, normalize it into a deterministic fixture and document the
  command used.
- Try to obtain a Reaper-like report fixture. If unavailable, document the gap
  and implement only the explicit skip path.

### Acceptance

- `docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md` exists.
- Fixture files exist under the extractor fixture directory.
- The spec is updated if the tool output invalidates parser assumptions.

## Task 1 - Pydantic Models

### Tests First

Create `test_dead_symbol_binary_surface_models.py` covering:

- valid `DeadSymbolCandidate`;
- valid `BinarySurfaceRecord`;
- invalid empty symbol key when no file/line fallback exists;
- frozen model behavior;
- confidence enum rejects unknown values;
- candidate state / skip reason combinations.

### Implementation

Add frozen Pydantic v2 models under
`extractors/dead_symbol_binary_surface/models.py`.

### Acceptance

`uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface_models.py -v`
passes.

## Task 2 - Periphery Parser

### Tests First

Create parser tests for:

- unused Swift class/function/property output;
- public retained symbol;
- generated path skipped;
- dynamic entry point skipped;
- malformed finding produces warning, not crash;
- deterministic normalized symbol key.

### Implementation

Add `parsers/periphery.py` that returns normalized findings and parser warnings.
Keep raw output parsing isolated from graph models.

### Acceptance

Targeted Periphery parser tests pass and no production graph code is touched.

## Task 3 - Reaper Path Or Explicit Skip

### Tests First

If a report fixture exists:

- parse runtime-unseen class;
- parse used class;
- parse timestamp/app-version metadata;
- downgrade unsupported Swift generic or collision cases to lower confidence.

If no fixture exists:

- test `reaper_report_unavailable` skip metric;
- verify extractor still succeeds with Periphery-only evidence.

### Implementation

Add `parsers/reaper.py` with either parser or no-op skip implementation.

### Acceptance

Reaper tests document the chosen v1 behavior explicitly.

## Task 4 - Correlation And Safety Guards

### Tests First

Create `test_dead_symbol_binary_surface_correlation.py` covering:

- exact match to `PublicApiSymbol.symbol_qualified_name`;
- exact match to Phase 1 symbol key;
- ambiguous match skipped;
- public/open API retained;
- GIM-192 consumed symbol blocked;
- missing key low-confidence or skipped according to spec.

### Implementation

Add correlation helper and safety guard functions. Do not query fuzzy matches.

### Acceptance

All correlation tests pass and include negative cases for each forbidden fallback.

## Task 5 - Neo4j Schema And Writer

### Tests First

Writer unit tests should assert:

- unique constraints for candidate and binary-surface IDs;
- `MERGE` creates nodes once;
- re-run consumes `ResultSummary` counters and reports zero created rows;
- blocker edges are created only when referenced nodes exist.

### Implementation

Extend `foundation/schema.py` and add `neo4j_writer.py`.

### Acceptance

Unit tests prove idempotency at writer level.

## Task 6 - Extractor Orchestrator

### Tests First

Create orchestrator tests for:

- Periphery-only happy path;
- missing Periphery file returns explicit warning;
- Reaper unavailable does not fail;
- CodeQL unavailable does not fail;
- stats counters align with writer counters.

### Implementation

Add `extractor.py` and package `__init__.py`. Register only after tests pass.

### Acceptance

`uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface*.py -q`
passes.

## Task 7 - Integration Fixture

### Tests First

Create an integration test that sets up:

- one used Swift symbol;
- one unused Swift symbol;
- one public retained symbol;
- one generated/dynamic skipped symbol;
- optional GIM-192 contract blocker node.

### Implementation

Add the fixture and graph setup. The fixture must be small and deterministic.

### Acceptance

`uv run pytest tests/extractors/integration/test_dead_symbol_binary_surface_integration.py -v`
passes and asserts direct Neo4j graph invariants.

## Task 8 - Runbook

### Work

Add `docs/runbooks/dead-symbol-binary-surface.md` with:

- required pre-generated tool output paths;
- Periphery command used for the fixture;
- optional Reaper evidence path;
- direct Neo4j queries for candidates, retained public API, blockers, and skips;
- false-positive warnings for incomplete target builds.

### Acceptance

Runbook commands match test names and fixture paths.

## Task 9 - Validation Bundle

Implementation handoff must include:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface*.py
uv run pytest tests/extractors/integration/test_dead_symbol_binary_surface_integration.py -v
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
```

If Docker/testcontainers is required and unavailable locally, implementation must
wait for GitHub CI and cite the exact run URL and failing/passing test name.

## Rollback

- Remove `dead_symbol_binary_surface` from `extractors/registry.py`.
- Drop only labels/constraints introduced for `DeadSymbolCandidate` and
  `BinarySurfaceRecord` if no other extractor has started using them.
- Leave fixture docs and research spike for post-mortem unless operator asks for
  cleanup.

## Review Checklist

CXCodeReviewer must verify:

- No public MCP/API/router files changed.
- No production app build files modified to install Reaper or Periphery.
- No auto-delete behavior exists.
- Public API and contract blockers are represented as retention/blocking facts.
- Reaper and CodeQL absence are explicit skip paths, not silent green paths.
- Idempotency is proven with Neo4j counters, not just object counts.
