# GIM-1661 W5 design gate - `trace_call_path` call-graph coverage

Date: 2026-06-17.
Issue: `GIM-1661`.
Grounded repo state: `origin/develop` at `5d5fd4709756fbc93de0d6c201297764c858512e`.
Previous slice: W4 merged as `5d5fd4709756fbc93de0d6c201297764c858512e`.

## Goal

Restore useful caller coverage for `palace.code.trace_call_path` on Palace-known
projects without waiting for a live restart or a new ingest window, and make
`call graph missing` distinct from `symbol has no callers`.

## Evidence

- The approved June 7 native-passthrough spec already selected symbol-graph
  traversal over `REFERENCES | CONFORMS_TO | EXTENDS | EXTENSION_OF |
  EXISTENTIAL_USE` for Phase 1 `trace_call_path`:
  `docs/superpowers/specs/2026-06-07-palace-mcp-native-passthrough-unification.md`.
- The June 1 physical probe documented that the Swift graph has no `CALLS`
  edges, so a `CALLS`-only traversal returns empty even for known call sites:
  `docs/research/gimle-physical-test-2026-06-01.md`.
- The current implementation regressed to `CALL_EDGES = {"CALLS"}` in
  `services/palace-mcp/src/palace_mcp/code/edges.py`, while the ingest pipeline
  still writes `REFERENCES`, `CONFORMS_TO`, `EXTENDS`, and `EXTENSION_OF` via
  `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`.
- `PALACE_INDEXSTORE_PATHS` is optional and the issue's re-probe says it is not
  configured for the live environment, so `call_hierarchy` cannot be the slice's
  primary substrate.

## Decision

Use the already-ingested Palace symbol relationships as the W5 caller substrate:

- Expand `trace_call_path` traversal from `CALLS`-only to
  `CALLS | REFERENCES | CONFORMS_TO | EXTENDS | EXTENSION_OF | EXISTENTIAL_USE`.
- When a trace returns no rows, run one scoped `has any traversable edge`
  check for the project.
- If the project has zero traversable edges, return
  `{ok: false, error_code: "not_extracted"}`.
- If the project has traversable edges, return the normal success envelope with
  empty `callers` / `callees`.

This is the smallest change that satisfies W5 without inventing a new extractor
or depending on unavailable IndexStore configuration.

## Rejected alternatives

### 1. Configure or wire IndexStoreDB via `PALACE_INDEXSTORE_PATHS`

Rejected for W5.

- The issue body says the required env is not configured.
- Live validation is deferred until a later CTO-controlled restart/re-ingest
  window, so this slice cannot rely on operator configuration landing first.
- `palace.code.call_hierarchy` is still valuable as a higher-fidelity future
  substrate, but it is not presently universal across Palace-known projects.

### 2. Add a dedicated call-edge extractor

Rejected for W5.

- A new extractor would require new ingest logic, backfill, and operational
  rollout before `trace_call_path` improves.
- The issue explicitly scopes W5 to this workstream only and defers live
  validation until after restart plus re-ingest.
- That is a larger Phase 2 investment, not the minimum fix for the current
  regression.

### 3. Keep `CALLS`-only and treat empty as success

Rejected.

- This is already disproven by the June 1 field probe: known Swift call sites
  produce empty traces because the graph lacks `CALLS`.
- It also collapses two distinct states: `no callers` and `call graph absent`.

## Accuracy limits

- `REFERENCES` is broader than expression-level `CALLS`. It can include symbol
  uses that are not direct runtime invocation edges.
- `CONFORMS_TO`, `EXTENDS`, `EXTENSION_OF`, and `EXISTENTIAL_USE` widen
  reachability further. This matches the existing Phase 1 graph-reachability
  contract rather than a strict compiler call graph.
- For this slice, that tradeoff is acceptable because the goal is restoring
  caller coverage and making substrate state explicit, not proving exact Swift
  dispatch semantics.

## `not_extracted` semantics

- `not_extracted` means: within the scoped project graph, there are zero edges
  of any traversable trace type.
- Empty `callers` / `callees` means: the project has traversable trace edges,
  but this symbol did not match any path under the requested direction/depth.

This keeps `trace_call_path` honest about substrate absence while preserving a
non-error empty result for genuine misses.

## Rollback

- The change is query-only plus tests. No stored data or schema migration is
  involved.
- If the broader traversal proves too noisy, rollback is a small revert of the
  edge registry and the `not_extracted` helper logic.
- A later higher-fidelity extractor or IndexStore-backed implementation can
  replace this slice without data cleanup.
