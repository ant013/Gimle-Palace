# GIM-217 - Reactive Dependency Tracer - Implementation Plan

Plan source of truth:
`docs/superpowers/specs/2026-05-06-GIM-217-reactive-dependency-tracer.md`.

This branch contains spec/plan only. It may be pushed for the urgent GIM-217
docs gate, but production implementation remains blocked until CX review
explicitly approves the rev2 spec and this plan.

## Goal

Implement `reactive_dependency_tracer`, a Swift-first extractor for reactive
state dependencies in SwiftUI/UIKit/Combine/async code, with Kotlin/Compose
schema support where it shares the same model. v1 consumes pre-generated Swift
helper JSON only; it must not execute a SwiftSyntax helper from the extractor
process.

## Phase 0 - Review Gate Before Code

Owner: Board/operator + CX review when explicitly started.

- [ ] Review the spec for Swift usefulness and extractor boundaries.
- [ ] Confirm pre-generated Swift helper JSON fixture/input path for v1.
- [ ] Confirm that live SwiftSyntax helper execution remains deferred until a
  hardened launcher spec exists.
- [ ] Confirm whether Kotlin/Compose implementation is part of this issue or a
  follow-up after Swift graph schema lands.
- [ ] Confirm graph labels and relationship names.
- [ ] Confirm launch smoke query:
  - "what changes when this state changes?"
  - "which state drives this view?"
- [ ] Do not proceed to implementation until this gate is explicitly approved.

## File Structure

| Path | Responsibility |
|---|---|
| `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/__init__.py` | Export extractor |
| `.../models.py` | Strict Pydantic models and enums |
| `.../identifiers.py` | Stable ID helpers |
| `.../swift_helper_contract.py` | Versioned helper JSON parser |
| `.../diagnostics.py` | Structured skip/warning diagnostic records |
| `.../normalizer.py` | State/effect/edge normalization |
| `.../confidence.py` | Confidence scoring |
| `.../file_discovery.py` | Swift/Kotlin source discovery and skip filtering |
| `.../neo4j_writer.py` | Idempotent graph writer |
| `.../extractor.py` | `ReactiveDependencyTracerExtractor(BaseExtractor)` |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Register extractor |
| `services/palace-mcp/swift_reactive_probe/` | Future only; out of v1 unless launcher spec is approved |
| `services/palace-mcp/tests/extractors/fixtures/reactive-dependency-swift-mini/` | Swift fixture |
| `services/palace-mcp/tests/extractors/unit/test_reactive_dependency_tracer_*.py` | Unit tests |
| `services/palace-mcp/tests/extractors/integration/test_reactive_dependency_tracer_integration.py` | Real Neo4j integration |
| `docs/runbooks/reactive-dependency-tracer.md` | Operator runbook |
| `CLAUDE.md` | Registered extractor/operator workflow |

## Task 1 - Models And Stable IDs

Files:

- `reactive_dependency_tracer/models.py`
- `reactive_dependency_tracer/identifiers.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_models.py`

Steps:

- [ ] Write failing tests for `ReactiveComponent`, `ReactiveState`,
  `ReactiveEffect`, `ReactiveDiagnostic`, and relationship/event records.
- [ ] Enforce `ConfigDict(frozen=True, extra='forbid')`.
- [ ] Validate enums from the spec exactly.
- [ ] Add stable ID helpers based on group/project/commit/language/path/name/ref.
- [ ] Add `resolution_status` enum: `syntax_exact`, `syntax_heuristic`,
  `symbol_correlated`, `macro_unexpanded`, `type_unresolved`.
- [ ] Add tests proving IDs are deterministic and change only when identity
  fields change.

Acceptance:

- `uv run pytest services/palace-mcp/tests/extractors/unit/test_reactive_dependency_tracer_models.py -v`

Commit:

- `feat(GIM-217): add reactive dependency models and stable IDs`

## Task 2 - Swift Helper JSON Contract Parser

Files:

- `reactive_dependency_tracer/swift_helper_contract.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_swift_contract.py`

Steps:

- [ ] Write parser tests for a valid helper JSON document.
- [ ] Reject unknown top-level keys.
- [ ] Reject unsupported `schema_version`.
- [ ] Require deterministic refs: `component_ref`, `state_ref`, `effect_ref`,
  `edge_ref`, `from_ref`, `to_ref`, `owner_component_ref`.
- [ ] Require `module_name`, `edge_kind`, ranges, `access_path`,
  `binding_kind`, `trigger_expression_kind`, and `resolution_status` where
  specified by the spec.
- [ ] Reject dangling refs, duplicate refs inside a file, unsupported
  `edge_kind`, and missing ownership refs.
- [ ] Reject absolute paths outside repo root.
- [ ] Reject `..`, empty paths, symlink escapes, Windows separators, and home
  paths.
- [ ] Accept file-level parse warnings without failing the full document.
- [ ] Enforce output bounds: files, JSON bytes, warnings, edges per file.
- [ ] Ensure raw source snippets are not accepted as model fields.
- [ ] Ensure diagnostic/warning records use structured codes and redacted,
  bounded messages.

Acceptance:

- Parser unit tests pass.

Commit:

- `feat(GIM-217): parse Swift reactive helper contract`

## Task 3 - Source Discovery And Diagnostics

Files:

- `reactive_dependency_tracer/file_discovery.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_discovery.py`

Steps:

- [ ] Discover `*.swift` files under repo root.
- [ ] Exclude `.build`, `DerivedData`, `Pods`, `.swiftpm`, generated folders,
  vendored folders, and configured ignore paths.
- [ ] Add file-size cap and `swift_file_too_large` skip.
- [ ] Add generated/vendor skip reasons.
- [ ] Add Kotlin file discovery as optional metadata, not a blocker.
- [ ] Create `ReactiveDiagnostic` records for skipped files instead of relying
  on logs or `IngestRun` extras.

Acceptance:

- Discovery tests cover normal Swift files, generated files, vendor files,
  large files, and no-Swift projects.

Commit:

- `feat(GIM-217): discover Swift sources and persist diagnostics`

## Task 4 - Swift Normalization

Files:

- `reactive_dependency_tracer/normalizer.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_normalizer.py`

Steps:

- [ ] Normalize Swift property wrappers to `state_kind`.
- [ ] Normalize Observation framework declarations.
- [ ] Normalize Combine publisher/operator/sink facts.
- [ ] Normalize SwiftUI lifecycle modifiers.
- [ ] Normalize UIKit target/action and delegate candidates.
- [ ] Preserve line ranges and repo-relative paths.
- [ ] Preserve and propagate `resolution_status`.
- [ ] Treat `.task {}`, `.onAppear`, and `.onDisappear` as lifecycle effects,
  not state-trigger edges.
- [ ] Create `TRIGGERS_EFFECT` only for explicit trigger evidence:
  `.task(id:)`, `.onChange(of:)`, `.onReceive`, binding/write access, or
  equivalent state access.
- [ ] Emit `symbol_correlation_unavailable` diagnostic when no exact symbol key
  exists.

Acceptance:

- Tests cover `@State`, `@Binding`, `@ObservedObject`, `@StateObject`,
  `@Environment`, `@Published`, `@Observable`, `.sink`, `.assign`,
  `.onChange`, `.task(id:)`, lifecycle-only `.task`, `.onAppear`, and UIKit
  callback candidates.

Commit:

- `feat(GIM-217): normalize Swift reactive facts`

## Task 5 - Confidence Scoring

Files:

- `reactive_dependency_tracer/confidence.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_confidence.py`

Steps:

- [ ] Score direct lexical declaration/read/write as `high` with
  `resolution_status='syntax_exact'`.
- [ ] Score exact symbol correlation or local same-file owner correlation as
  `medium`.
- [ ] Score callback/delegate/notification/dynamic facts as `low`.
- [ ] Add downgrade for unresolved owner/type.
- [ ] Add downgrade for macro-decorated declarations when not expanded.
- [ ] Ensure `type_unresolved` and `syntax_heuristic` facts cannot become
  `high`.

Acceptance:

- Confidence tests are table-driven and include downgrade cases.

Commit:

- `feat(GIM-217): score reactive dependency confidence`

## Task 6 - Neo4j Writer

Files:

- `reactive_dependency_tracer/neo4j_writer.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_neo4j_writer.py`

Steps:

- [ ] Declare extractor-local constraints and indexes.
- [ ] Write idempotent `MERGE` for `ReactiveComponent`, `ReactiveState`, and
  `ReactiveEffect`, plus `ReactiveDiagnostic`.
- [ ] Write relationship `MERGE`s with stable identity properties.
- [ ] Replace only facts owned by `source='extractor.reactive_dependency_tracer'`
  for the same project, commit, language, and exact validated file paths.
- [ ] Never delete facts for a file until replacement facts and diagnostics for
  that same file have passed validation.
- [ ] Add partial-rerun preservation tests: one invalid batch must not delete
  unrelated files, commits, projects, or languages.
- [ ] Ensure no `SymbolOccurrenceShadow` or `PublicApiSymbol` nodes are deleted
  or mutated by this writer.
- [ ] Return exact node and edge counters.

Acceptance:

- Unit tests validate generated Cypher shape, counter behavior, diagnostic
  persistence, and partial-rerun preservation.

Commit:

- `feat(GIM-217): write reactive dependency graph facts`

## Task 7 - Extractor Orchestrator

Files:

- `reactive_dependency_tracer/extractor.py`
- `reactive_dependency_tracer/__init__.py`
- `tests/extractors/unit/test_reactive_dependency_tracer_extractor.py`

Steps:

- [ ] Implement `ReactiveDependencyTracerExtractor(BaseExtractor)`.
- [ ] Follow `BaseExtractor.run(graphiti, ctx) -> ExtractorStats`.
- [ ] Run source discovery.
- [ ] Read pre-generated helper JSON from the approved fixture/input path.
- [ ] Do not launch helper binaries in v1.
- [ ] Convert missing helper JSON into persisted `ReactiveDiagnostic` skip
  records.
- [ ] Normalize and write graph facts in batches.
- [ ] Ensure exceptions use existing extractor error patterns.
- [ ] Sanitize exception text before any message can reach diagnostics or
  `IngestRun.errors`.

Acceptance:

- Unit tests cover happy path, missing helper JSON skip, parse failure skip, all
  Swift files failing, and sanitized exception messages.

Commit:

- `feat(GIM-217): orchestrate reactive dependency extractor`

## Task 8 - Helper Launcher Deferred / Fixture Contract Lock

Live SwiftSyntax helper execution is out of v1. This task locks the committed
fixture JSON contract and records the future launcher requirements so no worker
quietly adds unsafe subprocess execution.

Files:

- `tests/extractors/fixtures/reactive-dependency-swift-mini/reactive_facts.json`
- `tests/extractors/fixtures/reactive-dependency-swift-mini/REGEN.md`
- `docs/runbooks/reactive-dependency-tracer.md`

Steps:

- [ ] Commit reviewed pre-generated helper JSON for the Swift fixture.
- [ ] Add a validator test that the fixture JSON exercises all required record
  fields and structured diagnostics.
- [ ] Document that live helper execution requires a future hardened launcher:
  no shell, fixed trusted binary path, sanitized env, `stdin=DEVNULL`, bounded
  stdout/stderr, timeout, process-group kill/drain, no inherited user config.
- [ ] Add a guard test or TODO marker so implementation cannot call
  `subprocess` from this package in v1.

Acceptance:

- Fixture JSON contract tests pass; no live helper process is invoked.

Commit:

- `test(GIM-217): lock Swift reactive helper JSON contract`

## Task 9 - Swift Fixture

Files:

- `tests/extractors/fixtures/reactive-dependency-swift-mini/`
- `tests/extractors/fixtures/reactive-dependency-swift-mini/REGEN.md`

Steps:

- [ ] Add a minimal Swift fixture with:
  - SwiftUI `@State` and `@Binding`;
  - `ObservableObject` + `@Published` or `@Observable`;
  - Combine `sink` or `assign`;
  - `.task(id:)` or `.onChange`;
  - lifecycle-only `.task {}` or `.onAppear` that does not create a
    `TRIGGERS_EFFECT` edge;
  - UIKit target/action or delegate candidate;
  - generated/vendor file skip example.
- [ ] Add expected helper JSON with component/state/effect/edge refs,
  `resolution_status`, ranges, and diagnostics.
- [ ] Document fixture regeneration.

Acceptance:

- Fixture unit tests consume committed fixture data.

Commit:

- `test(GIM-217): add Swift reactive dependency fixture`

## Task 10 - Integration Test

Files:

- `tests/extractors/integration/test_reactive_dependency_tracer_integration.py`

Steps:

- [ ] Run extractor against Swift fixture and real Neo4j.
- [ ] Assert required node labels exist.
- [ ] Assert required relationship kinds exist.
- [ ] Assert at least one high-confidence and one low-confidence flow.
- [ ] Assert idempotent rerun counts.
- [ ] Assert `ReactiveDiagnostic` skip records are queryable.
- [ ] Assert lifecycle-only effects do not create state trigger edges.
- [ ] Assert partial invalid batch preserves facts for unrelated files.

Acceptance:

- Integration test passes under the repo's Neo4j test pattern.

Commit:

- `test(GIM-217): integrate reactive dependency tracer with Neo4j`

## Task 11 - Registry And Runner Wiring

Files:

- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- existing registry tests

Steps:

- [ ] Register `reactive_dependency_tracer`.
- [ ] Ensure schema declarations are included by extractor schema bootstrap.
- [ ] Add registry test for lookup/listing.

Acceptance:

- Registry tests pass.

Commit:

- `feat(GIM-217): register reactive dependency tracer`

## Task 12 - Kotlin/Compose Placeholder Or Implementation

Scope depends on Phase 0.

Files:

- `reactive_dependency_tracer/kotlin_contract.py` if implemented
- `tests/extractors/unit/test_reactive_dependency_tracer_kotlin.py`

Steps:

- [ ] If not implementing Kotlin in v1, emit `kotlin_tooling_unavailable` or
  `compose_stability_report_unavailable` structured skips.
- [ ] If implementing Kotlin in v1, parse a reviewed detekt/Compose contract,
  not ad hoc text output.
- [ ] Ensure Kotlin facts do not block Swift extraction.

Acceptance:

- Swift tests pass whether Kotlin tooling is present or absent.

Commit:

- `feat(GIM-217): add Kotlin reactive tracing skip path`

## Task 13 - Runbook And Operator Query

Files:

- `docs/runbooks/reactive-dependency-tracer.md`
- `CLAUDE.md`

Steps:

- [ ] Document extractor purpose and Swift-first scope.
- [ ] Document pre-generated JSON workflow.
- [ ] Document future helper launcher constraints; do not document a live helper
  execution path for v1.
- [ ] Document environment/config flags.
- [ ] Add sample Cypher:
  - explicit trigger state -> effects;
  - view -> driving states;
  - lifecycle-only effects;
  - low-confidence callback candidates.
- [ ] Add troubleshooting for missing helper, parse failures, generated files,
  and missing symbol correlation.
- [ ] Add `CLAUDE.md` extractor table row.

Acceptance:

- Runbook is enough for an operator to run the fixture smoke.

Commit:

- `docs(GIM-217): document reactive dependency tracer workflow`

## Task 14 - Verification Sweep

Steps:

- [ ] Run focused unit tests.
- [ ] Run integration test.
- [ ] Run registry tests.
- [ ] Run lint/format if touched files require it.
- [ ] Inspect graph counts, idempotency evidence, and partial-rerun preservation.
- [ ] Confirm no raw source snippets or absolute home paths are persisted.
- [ ] Confirm `ReactiveDiagnostic` nodes exist for skipped/invalid records.
- [ ] Confirm `IngestRun.errors` is sanitized on failure paths.
- [ ] Post evidence only after the operator starts the issue/phase chain.

Expected commands:

```bash
uv run pytest services/palace-mcp/tests/extractors/unit/test_reactive_dependency_tracer_*.py -v
uv run pytest services/palace-mcp/tests/extractors/integration/test_reactive_dependency_tracer_integration.py -v
uv run pytest services/palace-mcp/tests/extractors/test_registry.py -v
```

## Review Checklist

- [ ] Swift useful path is mandatory and tested.
- [ ] Kotlin/Compose cannot block Swift extraction.
- [ ] No target code execution.
- [ ] No build task execution.
- [ ] Helper output is strict, bounded, and treated as untrusted input.
- [ ] v1 does not execute a SwiftSyntax helper process.
- [ ] Graph ownership does not delete facts from other extractors.
- [ ] Exact symbol correlation only; no fuzzy matching.
- [ ] Structured skips are persisted as `ReactiveDiagnostic`, not log-only.
- [ ] Partial reruns cannot delete unrelated file/commit facts.
- [ ] Lifecycle effects are not conflated with state-triggered effects.
- [ ] Path/redaction tests cover `..`, empty, symlink, Windows separator, home
  path, raw snippet, and exception-text cases.
- [ ] Idempotent reruns are proven.
- [ ] Runbook includes practical Swift smoke queries.
