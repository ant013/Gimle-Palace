---
slug: reactive-dependency-tracer
status: proposed (rev3)
branch: feature/GIM-217-reactive-dependency-tracer
paperclip_issue: 217
authoring_team: Board/Codex spec draft for CX review
team: CX
predecessor: 5155ef7 (origin/develop, post GIM-215 tooling/security spike)
date: 2026-05-06
roadmap_item: "Phase 2 #3 Reactive Dependency Tracer"
roadmap_source: "docs/roadmap.md §2.1 Structural, row #3"
plan: docs/superpowers/plans/2026-05-06-GIM-217-reactive-dependency-tracer.md
rev2_changes: |
  Addressed read-only audit blockers before implementation:
  - v1 is explicitly syntax-only and pre-generated JSON only; live SwiftSyntax
    helper execution is deferred until a hardened launcher spec exists;
  - added resolution_status to graph facts and helper records;
  - replaced non-implementable IngestRun extras skip persistence with dedicated
    ReactiveDiagnostic nodes;
  - expanded the Swift helper JSON contract with deterministic refs, ownership,
    ranges, edge kinds, and structured warning/skip codes;
  - hardened replace/delete policy to per-file successful-batch replacement
    with partial-rerun preservation tests;
  - separated lifecycle effects from state-triggered effects;
  - defined exact symbol correlation targets and path/redaction tests.
rev3_changes: |
  Addressed CXCodeReviewer Phase 1.2 request-changes items:
  - froze Kotlin/Compose v1 scope to structured skip only; no Kotlin parser
    or detekt/Compose contract implementation is authorized in this slice;
  - removed Kotlin/Compose implementation from open questions;
  - fixed verification command expectations in the implementation plan.
---

# GIM-217 - Reactive Dependency Tracer

## 1. Goal

Build a Swift-first extractor named `reactive_dependency_tracer` that records
how state changes propagate through Swift UI and application code.

The extractor answers:

- Which Swift declarations are reactive state sources?
- Which views, view models, closures, tasks, Combine pipelines, and callbacks
  read or write those state sources?
- Which state changes trigger effects such as render invalidation, sink/assign
  side effects, `.task`, `.onChange`, `.onReceive`, delegate callbacks, or
  explicit view-model mutations?
- Which reactive flows cross files, types, modules, or framework boundaries?
- Which facts are precise enough for downstream impact analysis, and which are
  only heuristic candidates?

The first-class happy path is Swift code. Kotlin/Compose runtime implementation
is deferred for v1; this slice keeps only shared schema readiness and structured
skip diagnostics so Swift acceptance criteria stay unambiguous.

## 2. Context

Roadmap row #3 is owned by CX with tool stack `swift-syntax + detekt AST +
Compose Stability`. The operator priority is now "run all extractors useful for
Swift code." This slice qualifies because reactive state propagation is central
to SwiftUI, UIKit view-models, Combine, and async UI tasks.

Adjacent extractor boundaries:

- Phase 1 symbol extractors provide symbol identity, but this slice must work on
  source syntax even when full symbol occurrence coverage is incomplete.
- GIM-190 Public API Surface records exported symbols. This extractor records
  reactive dependency flows, not API compatibility.
- GIM-192 Cross-Module Contract records public contract consumption. This
  extractor may link a reactive flow to a module boundary when known, but it
  does not replace contract extraction.
- GIM-215 Build System Extractor is running separately. This extractor must not
  require build task execution in v1.

## 3. Reference Basis

Primary references checked on 2026-05-06:

- SwiftSyntax is the official Swift package for source-accurate Swift syntax
  trees; releases align with Swift language/tooling releases. Source:
  <https://github.com/swiftlang/swift-syntax>.
- detekt type resolution enables deeper Kotlin analysis when classpath and
  compiler context are available; rules requiring full analysis must not run
  without the required context. Source:
  <https://detekt.dev/docs/gettingstarted/type-resolution/>.
- Compose stability affects recomposition behavior because stable parameters may
  be skipped while unstable parameters force recomposition. Source:
  <https://developer.android.com/develop/ui/compose/performance/stability>.

## 4. Assumptions

- Swift is mandatory for v1. Kotlin/Compose parser and contract implementation
  are deferred; v1 represents Kotlin/Compose only through schema-ready enums and
  structured skip diagnostics.
- The extractor parses source files and pre-generated helper outputs. It must not
  run `xcodebuild`, Gradle build tasks, app tests, or app binaries.
- v1 ingests pre-generated Swift helper JSON only. Building or executing a
  SwiftSyntax helper from the extractor process is out of scope until a separate
  hardened launcher design is approved.
- A future SwiftSyntax helper is acceptable only if it is built from trusted
  repository code, not from the target repository being analyzed.
- Macro expansion is out of scope for v1. Macro annotations and macro-decorated
  declarations are recorded as syntax facts with `macro_expansion_status =
  'not_expanded'`.
- Full type resolution is out of scope for v1. The extractor must label every
  fact with `resolution_status` so callers can distinguish exact syntax,
  heuristic syntax, symbol-correlated facts, unexpanded macros, and unresolved
  types.
- Dynamic dispatch, Objective-C runtime callbacks, KVO, notification names, and
  UIKit target/action wiring are heuristic unless backed by an explicit syntax
  pattern.
- The extractor is read-only. It does not propose code changes or claim a flow
  is a bug by itself.

## 5. Scope

### In Scope

- New extractor identity: `reactive_dependency_tracer`.
- Pre-generated Swift helper JSON contract for Swift source facts:
  - reactive state declarations;
  - reads and writes of those declarations;
  - SwiftUI property wrappers and environment reads;
  - Observation framework patterns (`@Observable`, `@Bindable`, `withObservationTracking`
    when syntactically visible);
  - `ObservableObject`, `@Published`, `objectWillChange`;
  - Combine publishers, operators, `sink`, `assign`, `onReceive`;
  - SwiftUI `.onChange`, `.task`, `.onAppear`, `.onDisappear`, `.sheet`,
    `.navigationDestination`, and binding-producing expressions;
  - UIKit target/action and delegate assignment candidates;
  - async sequences and `Task` closures that read or write reactive state.
  The v1 implementation consumes this JSON; it does not launch the helper.
- Pydantic models with `extra='forbid'` and deterministic IDs.
- Graph nodes for components, reactive state, effects, and flow observations.
- Graph relationships for read/write/bind/observe/trigger/propagate edges.
- Confidence model:
  - `high`: direct lexical state declaration/read/write in the same type or
    closure;
  - `medium`: exact symbol correlation or local same-file owner correlation;
  - `low`: stringly, dynamic, delegate, notification, Objective-C, or unresolved
    callback candidate.
- Swift fixture covering SwiftUI, Combine, async task, UIKit callback, and
  Observation framework syntax.
- Kotlin/Compose v1 scope is structured skip only:
  - no Kotlin parser, detekt contract, or Compose stability contract is
    implemented in this issue;
  - Kotlin files may be discovered only to emit `kotlin_tooling_unavailable`
    or `compose_stability_report_unavailable` diagnostics;
  - missing Kotlin tool context results in structured skip, not extractor
    failure.
- Extractor-local schema declarations via `BaseExtractor.constraints` and
  `BaseExtractor.indexes` unless a shared foundation index is proven necessary.
- Unit tests for helper JSON validation, normalization, deterministic IDs,
  confidence scoring, and skip behavior.
- Dedicated `ReactiveDiagnostic` nodes for persisted warnings/skips.
- Integration test for Neo4j writes, idempotent reruns, diagnostic persistence,
  and partial-rerun preservation.
- Runbook with Swift helper build/run instructions and fixture regeneration.

### Out Of Scope

- Executing app code, UI tests, previews, build tasks, package resolution, or
  Gradle/Xcode builds as part of extraction.
- Executing the SwiftSyntax helper from the extractor process in v1.
- Full dataflow analysis equivalent to CodeQL or compiler SSA.
- Macro expansion and generated code reconstruction.
- Runtime recomposition profiling.
- Proving that a reactive dependency is wrong, inefficient, or flaky.
- Taint analysis, PII flow analysis, network schema extraction, or event-bus
  protocol extraction.
- Automatic issue creation, assignment, or PR creation from findings.
- Fuzzy matching across unrelated languages.

## 6. Data Model

### `ReactiveComponent`

Represents a Swift type, function, closure, view body, Combine pipeline, UIKit
controller method, or Kotlin composable scope that contains reactive facts.

Required properties:

- `id`: stable hash of `group_id`, `project`, `commit_sha`, `language`,
  `component_kind`, `qualified_name`, `file_path`, `start_line`.
- `group_id`
- `project`
- `commit_sha`
- `language`: `swift`, `kotlin`, or `unknown`.
- `module_name`
- `file_path`
- `qualified_name`
- `display_name`
- `component_kind`: `swiftui_view`, `observable_type`, `view_model`,
  `function`, `closure`, `combine_pipeline`, `uikit_controller`,
  `composable`, `unknown`.
- `start_line`
- `end_line`
- `range`: `{start_line, start_col, end_line, end_col}` copied from the helper
  and validated as non-negative.
- `resolution_status`: `syntax_exact`, `syntax_heuristic`,
  `symbol_correlated`, `macro_unexpanded`, or `type_unresolved`.
- `schema_version`
- `source`: `extractor.reactive_dependency_tracer`

### `ReactiveState`

Represents a state-bearing declaration or external reactive source.

Required properties:

- `id`: stable hash of `group_id`, `project`, `commit_sha`, `language`,
  `owner_qualified_name`, `state_name`, `state_kind`, `file_path`.
- `group_id`
- `project`
- `commit_sha`
- `language`
- `module_name`
- `file_path`
- `owner_qualified_name`
- `state_name`
- `declared_type`: nullable
- `state_kind`: `state`, `binding`, `observable`, `observable_object`,
  `published`, `environment`, `environment_object`, `publisher`,
  `subject`, `async_sequence`, `callback`, `delegate`, `notification`,
  `compose_state`, `flow`, `unknown`.
- `wrapper_or_api`: nullable, e.g. `@State`, `@Binding`, `@Published`,
  `PassthroughSubject`, `StateFlow`, `remember`.
- `macro_expansion_status`: `not_applicable`, `not_expanded`, `expanded`,
  `unknown`.
- `resolution_status`: `syntax_exact`, `syntax_heuristic`,
  `symbol_correlated`, `macro_unexpanded`, or `type_unresolved`.
- `confidence`
- `schema_version`
- `source`

### `ReactiveEffect`

Represents an effect or sink triggered by a reactive source.

Required properties:

- `id`: stable hash of `group_id`, `project`, `commit_sha`, `language`,
  `component_id`, `effect_kind`, `file_path`, `start_line`, `callee_name`.
- `component_id`
- `effect_kind`: `render`, `sink`, `assign`, `task`, `on_change`,
  `on_receive`, `callback`, `delegate_call`, `navigation`, `presentation`,
  `network_call_candidate`, `storage_write_candidate`, `unknown`.
- `callee_name`: nullable
- `file_path`
- `start_line`
- `end_line`
- `range`: `{start_line, start_col, end_line, end_col}`.
- `trigger_expression_kind`: nullable. Required for state-triggered effects.
  Values: `on_change_of`, `on_receive_publisher`, `task_id`, `binding_write`,
  `state_write`, `publisher_sink`, `lifecycle`, `unknown`.
- `resolution_status`: `syntax_exact`, `syntax_heuristic`,
  `symbol_correlated`, `macro_unexpanded`, or `type_unresolved`.
- `confidence`
- `source`
- `schema_version`

Lifecycle-only facts such as `.task {}` without `id:`, `.onAppear`, and
`.onDisappear` are effects in a component, but they are not automatically
`ReactiveState -> TRIGGERS_EFFECT` edges. The writer may create
`(ReactiveEffect)-[:IN_COMPONENT]->(ReactiveComponent)` for lifecycle effects;
it creates `TRIGGERS_EFFECT` only when the helper record has an explicit trigger
expression (`.task(id:)`, `.onChange(of:)`, `.onReceive`, binding/write access,
or equivalent state access evidence).

### `ReactiveDiagnostic`

Dedicated persisted diagnostic/skip node. This is required because the current
runner `ExtractorStats` and `:IngestRun` finalize path only persist counts,
errors, and success. Do not rely on logs or hypothetical IngestRun extras.

Required properties:

- `id`: stable hash of `group_id`, `project`, `commit_sha`,
  `diagnostic_code`, `file_path`, `range`, `ref`.
- `group_id`
- `project`
- `commit_sha`
- `run_id`
- `language`
- `file_path`: nullable for run-level diagnostics.
- `ref`: nullable helper ref (`component_ref`, `state_ref`, `effect_ref`,
  or `edge_ref`).
- `diagnostic_code`: one of the structured skip/warning codes in §10.
- `severity`: `info`, `warning`, or `error`.
- `message_redacted`: optional bounded, sanitized message. It must not contain
  raw source snippets, user home paths, or raw exception text.
- `range`: nullable `{start_line, start_col, end_line, end_col}`.
- `source`: `extractor.reactive_dependency_tracer`
- `schema_version`

### Relationships

- `(ReactiveComponent)-[:DECLARES_STATE]->(ReactiveState)`
- `(ReactiveComponent)-[:READS_STATE {confidence, access_path, line}]->(ReactiveState)`
- `(ReactiveComponent)-[:WRITES_STATE {confidence, access_path, line}]->(ReactiveState)`
- `(ReactiveState)-[:BINDS_TO {binding_kind, confidence, line}]->(ReactiveState)`
- `(ReactiveState)-[:TRIGGERS_EFFECT {trigger_kind, confidence, line}]->(ReactiveEffect)`
- `(ReactiveEffect)-[:IN_COMPONENT]->(ReactiveComponent)`
- `(ReactiveComponent)-[:CALLS_REACTIVE_COMPONENT {confidence, line}]->(ReactiveComponent)`
- `(ReactiveComponent)-[:CORRELATES_SYMBOL {symbol_key, target_label,
  confidence}]->(SymbolOccurrenceShadow)` only by exact `symbol_id` /
  `symbol_qualified_name` match.
- `(ReactiveComponent)-[:CORRELATES_PUBLIC_API {symbol_key, confidence}]
  ->(PublicApiSymbol)` only by exact `PublicApiSymbol.symbol_qualified_name`
  match for exported symbols.
- `(ReactiveDiagnostic)-[:DIAGNOSTIC_FOR]->(ReactiveComponent|ReactiveState|ReactiveEffect)`
  when the diagnostic has a matching helper ref.

Relationship IDs must be deterministic if relationships are represented as
nodes by the writer. If direct Neo4j relationships are used, writes must still
be idempotent by stable `MERGE` keys.

`SymbolOccurrenceShadow` is suitable for identity correlation only; it is not
commit/file consumer evidence. `PublicApiSymbol` is only used when the reactive
component/state is an exported symbol already represented by GIM-190. No
`(:Symbol)` label is assumed for this extractor.

## 7. Extraction Pipeline

1. Discover source roots and candidate files:
   - Swift: `*.swift`, excluding generated/vendor/build directories;
   - Kotlin: `*.kt`, optional until Swift path is complete.
2. Read pre-generated helper JSON from the approved fixture/input location.
   Live helper execution is not part of v1.
3. Validate helper JSON with strict Pydantic models before any graph deletion.
4. Normalize file paths, qualified names, state kinds, and confidence.
5. For Kotlin/Compose candidates, emit structured skip diagnostics only. Do
   not ingest Kotlin, detekt, or Compose facts in v1.
6. Correlate to existing `SymbolOccurrenceShadow` or `PublicApiSymbol` only when
   exact keys are available. No fuzzy matching in v1.
7. Write graph facts in idempotent batches:
   - delete/replace only facts with `source='extractor.reactive_dependency_tracer'`
     for the same project, commit, language, and exact validated file paths in
     the successful batch;
   - never delete facts for a file until that file's replacement records and
     diagnostics have passed validation;
   - if one batch fails validation, preserve previously written facts for other
     files and commits;
   - never delete symbol/public-api facts owned by other extractors.
8. Return `ExtractorStats` with precise node/edge counts.

## 8. Swift Helper JSON Contract

The helper emits one JSON document per run:

```json
{
  "tool_name": "palace-swift-reactive-probe",
  "tool_version": "0.1.0",
  "schema_version": 1,
  "swift_syntax_version": "string",
  "swift_toolchain": "string",
  "files": [
    {
      "path": "Sources/App/View.swift",
      "module_name": "App",
      "parse_status": "ok",
      "components": [
        {
          "component_ref": "c1",
          "module_name": "App",
          "component_kind": "swiftui_view",
          "qualified_name": "App.CounterView",
          "display_name": "CounterView",
          "range": {"start_line": 1, "start_col": 1, "end_line": 40, "end_col": 1},
          "resolution_status": "syntax_exact"
        }
      ],
      "states": [
        {
          "state_ref": "s1",
          "owner_component_ref": "c1",
          "module_name": "App",
          "state_name": "count",
          "state_kind": "state",
          "wrapper_or_api": "@State",
          "declared_type": "Int",
          "range": {"start_line": 3, "start_col": 5, "end_line": 3, "end_col": 29},
          "resolution_status": "syntax_exact"
        }
      ],
      "effects": [
        {
          "effect_ref": "e1",
          "owner_component_ref": "c1",
          "effect_kind": "on_change",
          "callee_name": "onChange",
          "trigger_expression_kind": "on_change_of",
          "range": {"start_line": 14, "start_col": 9, "end_line": 18, "end_col": 10},
          "resolution_status": "syntax_exact"
        }
      ],
      "edges": [
        {
          "edge_ref": "r1",
          "edge_kind": "triggers_effect",
          "from_ref": "s1",
          "to_ref": "e1",
          "owner_component_ref": "c1",
          "access_path": "count",
          "binding_kind": null,
          "trigger_expression_kind": "on_change_of",
          "range": {"start_line": 14, "start_col": 19, "end_line": 14, "end_col": 24},
          "confidence_hint": "high",
          "resolution_status": "syntax_exact"
        }
      ],
      "diagnostics": [
        {
          "code": "macro_unexpanded",
          "severity": "info",
          "ref": "c1",
          "message": "macro-decorated declaration recorded without expansion",
          "range": {"start_line": 1, "start_col": 1, "end_line": 1, "end_col": 12}
        }
      ]
    }
  ],
  "run_diagnostics": []
}
```

Contract requirements:

- Unknown top-level keys fail parser tests until reviewed.
- `path` must be repo-relative and normalized.
- Every component/state/effect/edge has a stable local ref unique within its
  file: `component_ref`, `state_ref`, `effect_ref`, or `edge_ref`.
- Ownership must be explicit:
  - states and effects require `owner_component_ref`;
  - edges require `from_ref`, `to_ref`, `edge_kind`, and `owner_component_ref`;
  - supported `edge_kind` values are `declares_state`, `reads_state`,
    `writes_state`, `binds_to`, `triggers_effect`, `has_lifecycle_effect`,
    `calls_reactive_component`.
- Ranges use `{start_line, start_col, end_line, end_col}` with 1-based lines and
  columns. Empty or negative ranges are rejected.
- `resolution_status` is required on every component/state/effect/edge.
- The helper must not emit raw source text. It may emit identifiers, qualified
  names, line/column ranges, and wrapper/API names.
- Parse failures for one file produce a file-level diagnostic and do not abort the
  whole extractor unless every Swift file fails.
- Diagnostics use structured codes from §10 and bounded redacted messages.
- The Python extractor owns graph IDs, not the helper.

## 9. Security And Safety

- No target repo code execution.
- No package manifest evaluation.
- No build task/action execution.
- No network access.
- v1 does not launch helper binaries. It reads pre-generated JSON only.
- No raw source snippets persisted in graph nodes or logs.
- Helper output is untrusted input and must be bounded:
  - max files per run;
  - max JSON bytes;
  - max warnings per file;
  - max edges per file.
- Absolute paths from helper output are rejected unless they normalize under
  `ctx.repo_path`.
- Parser warnings and error messages must redact user home directories.
- Tool absence is a structured skip, not a runner exception.

If a future revision enables live SwiftSyntax helper execution, it must add a
hardened launcher before implementation:

- no shell invocation;
- fixed trusted binary path outside the target repo;
- sanitized environment allowlist;
- `stdin=DEVNULL`;
- bounded stdout/stderr;
- per-batch timeout and batch-size cap;
- process-group kill and stdout/stderr drain on timeout;
- no inherited user config, package caches, or target repo build settings;
- launcher tests for timeout, oversized output, invalid JSON, and path escape.

## 10. Persisted Diagnostics And Structured Skips

The extractor must preserve skip/warning evidence as `ReactiveDiagnostic` nodes.
Do not use `:IngestRun` extras for v1 because the current runner persists only
`nodes_written`, `edges_written`, `errors`, and `success`. Do not leave skips in
stdout/stderr only.

Required skip reasons:

- `swift_helper_unavailable`
- `swift_helper_version_unsupported`
- `swift_parse_failed`
- `swift_file_too_large`
- `swift_generated_or_vendor_skipped`
- `kotlin_tooling_unavailable`
- `detekt_type_resolution_unavailable`
- `compose_stability_report_unavailable`
- `symbol_correlation_unavailable`
- `max_edges_per_file_exceeded`
- `invalid_helper_ref`
- `helper_json_too_large`
- `path_empty`
- `path_parent_traversal`
- `path_absolute_outside_repo`
- `path_symlink_escape`
- `path_windows_separator`
- `raw_source_snippet_rejected`
- `partial_batch_validation_failed`
- `macro_unexpanded`

Diagnostic persistence requirements:

- Run-level diagnostics use `file_path=null` and `ref=null`.
- File-level diagnostics include `file_path`.
- Ref-level diagnostics include `ref` from the helper JSON.
- Diagnostics must be written in the same per-file replacement transaction as
  the accepted facts for that file, or in a run-level diagnostic transaction for
  files that are skipped before fact parsing.
- Diagnostics count toward `ExtractorStats.nodes_written`.

## 11. Acceptance Criteria

1. `reactive_dependency_tracer` is registered and runnable through the extractor
   runner.
2. Swift helper JSON parser rejects unknown schema versions and unknown
   top-level keys, invalid refs, missing ownership refs, invalid ranges, and
   unsupported edge kinds.
3. Swift fixture produces at least:
   - one `@State` source;
   - one `@Binding` propagation;
   - one `@Published` / `ObservableObject` or `@Observable` source;
   - one Combine `sink` or `assign` effect;
   - one `.task` or `.onChange` effect;
   - one UIKit callback candidate.
4. Integration test writes `ReactiveComponent`, `ReactiveState`,
   `ReactiveEffect`, `ReactiveDiagnostic`, and all required relationship kinds
   to Neo4j.
5. Re-running the extractor on the same fixture is idempotent: node and edge
   counts do not grow.
6. Generated/vendor Swift files are skipped with structured reasons.
7. Missing Swift helper yields a successful structured skip when Swift files
   exist and policy allows skipping.
8. Kotlin/Compose absence does not block Swift extraction.
9. Exact symbol correlation works when fixture `SymbolOccurrenceShadow` or
   `PublicApiSymbol` nodes exist; missing symbols produce
   `symbol_correlation_unavailable`, not false edges.
10. No raw source snippets or absolute home paths are stored in graph properties.
11. Path validation rejects `..`, empty paths, symlink escapes, Windows
   separators, home paths, and absolute paths outside repo root.
12. Partial rerun preservation is tested: a failed/invalid batch cannot delete
   facts for unrelated files, languages, projects, or commits.
13. Lifecycle effects (`.task {}`, `.onAppear`) do not create
   `TRIGGERS_EFFECT` unless explicit trigger evidence exists.
14. Registry and runner tests follow existing `BaseExtractor` contract.
15. Runbook documents fixture JSON workflow, future helper launcher constraints,
   local smoke, and known
   false-positive classes.

## 12. Verification Plan

- Unit tests:
  - Pydantic models and ID determinism.
  - Swift helper JSON parser.
  - State/effect normalization.
  - Confidence scoring.
  - Skip behavior and path validation.
  - Diagnostic persistence.
  - Cypher writer idempotency.
  - Partial-rerun preservation.
- Integration tests:
  - Real Neo4j write/read on Swift fixture.
  - Idempotent rerun.
  - Missing helper JSON structured skip.
  - Invalid batch preserves unrelated files.
- Optional smoke:
  - Run against a small real Swift package or UW Swift fixture.
  - Query top reactive states and effects by module.

## 13. Open Questions For Review

1. Which repository path should hold the pre-generated helper JSON fixture
   contract for v1?
2. Should Observation framework support require Swift 5.9+ syntax fixture only,
   or should v1 also model legacy `ObservableObject` as the primary path?
3. Should UIKit target/action and delegate facts remain low-confidence in v1, or
   be excluded until a second slice with more precise type context?
4. Which downstream query should be considered the launch smoke:
   "what changes when this state changes?" or "which state drives this view?"

## 14. Initial File Impact

Expected implementation paths after spec approval:

- `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_reactive_dependency_tracer_*.py`
- `services/palace-mcp/tests/extractors/integration/test_reactive_dependency_tracer_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/reactive-dependency-swift-mini/`
- optional future `services/palace-mcp/swift_reactive_probe/` only after a
  hardened launcher spec is approved
- `docs/runbooks/reactive-dependency-tracer.md`
- `CLAUDE.md` registered extractor table

No implementation code is authorized by this draft.
