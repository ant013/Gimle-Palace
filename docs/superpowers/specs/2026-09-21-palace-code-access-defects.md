# Palace code access defects

Status: awaiting user approval
Branch: `fix/palace-code-access-defects`
Base: `origin/develop` at `ae80bea910451b5f5f6e101d1222b934dc4dfbe6`

## Goal

Make the native code access tools truthful and bounded for the three reported
cases: trace anchor resolution, generated-accessor results in semantic search,
and duplicated or unbounded response payloads.

Observable success means that an agent asking for a type-level call trace gets
the calls attached to that type's members (or an explicit resolution error),
semantic search returns one logical property result instead of Swift getter and
setter variants, and reference/trace responses expose bounded pagination
metadata without repeating the same occurrence list.

## Assumptions and open questions

- The current graph contains valid member symbols and call edges; this change
  is limited to access-layer resolution and response shaping.
- A type anchor expands to its callable members within the same project and
  preserves the requested direction and depth for each member.
- Existing clients can accept additive error and pagination fields.
- `occurrences_by_source_scope` will remain available as grouped metadata; the
  full occurrence objects will be returned once under `occurrences`.
- Open question: whether callers need an opt-in grouped occurrence payload for
  backwards compatibility. The default response will remove the duplicate;
  existing tests will determine whether an alias is required.

## Scope

In scope:

- `native_trace_call_path.py`: language-neutral anchor resolution, type/member
  expansion, anchor-not-found versus anchor-no-path versus project-not-extracted
  states, and standard pagination for paths/endpoints.
- `find_semantic.py` and its ranking tests: recognize Swift mangled accessor
  variants (`vg`/`vs`) and collapse getter/setter hits to one logical property
  before applying `limit`/`offset`.
- `code_composite.py` and find-references tests: remove duplicated occurrence
  objects while preserving source-scope counts and pagination metadata.

Out of scope:

- Rebuilding or changing SCIP/Neo4j extraction data.
- Redesigning the public semantic ranking formula.
- Adding new call-edge types or changing phase-2 trace modes.
- Reindexing production projects or changing deployment configuration.

## Affected files and areas

- `services/palace-mcp/src/palace_mcp/code/native_trace_call_path.py`
- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/code_composite.py`
- `services/palace-mcp/src/palace_mcp/pagination.py` (reuse only unless a
  narrowly required helper extension is proven)
- `services/palace-mcp/tests/code/test_native_trace_call_path.py`
- `services/palace-mcp/tests/code/test_ranking_contract.py`
- `services/palace-mcp/tests/code_composite/test_find_references_bundle.py`

## Verified analog family and delta matrix

| Slice | Primary/supporting analogs | Invariants to preserve | Required delta | Rejected delta | Failure modes | Tests before code |
|---|---|---|---|---|---|---|
| Trace anchor resolution | `native_trace_call_path`; existing trace envelope tests; `native_search_graph` as pagination counterexample | Project scoping, deprecated/test filtering, stable sorting, `FALLBACK_TO_CM`, phase-2 errors | Resolve exact/short/name anchors, expand type members, return explicit anchor state, paginate bounded path results | New graph relationships, extractor changes, unrelated call semantics | Unknown anchor, type with no callable members, member with no calls, mixed test paths, query truncation | Unknown anchor error; type anchor reaches member callers; empty member paths remain distinguishable from unindexed project; pagination boundary |
| Semantic accessor collapse | `_accessor_penalty` and ranking contract tests; embedding candidate policy as rejected counterexample | Existing score weights, source-scope ordering, canonical hit fields, limit/offset contract | Detect Swift accessor forms and collapse getter/setter variants by logical property identity before paging | Reweighting semantic scores, deleting all accessor data at ingest time, changing vector backend | Mangled name without recognizable suffix, getter only, setter only, unrelated symbols sharing a prefix | `vg`/`vs` canonicalize together; distinct files/properties remain distinct; result count and pagination are stable |
| Response envelope | `pagination_envelope`; `native_search_graph`; existing find-references bundle/project tests | `total`, `returned`, `offset`, `has_more`, `next_offset`, source-scope counts | Apply bounded pagination to trace and ensure occurrences are materialized once | Removing useful grouped counts, changing occurrence identity or Tantivy indexing | Partial page, empty page, grouped scope with dependencies, legacy consumer expecting old keys | No duplicate occurrence objects; grouped counts preserved; trace reports truncation and continuation |

## Acceptance criteria

1. `trace_call_path` never returns `ok=true` with an empty result for an anchor
   that is absent from the project. It returns a stable `anchor_not_found`
   error with project and mode.
2. A type/class anchor resolves to its members and returns inbound/outbound
   calls attached to those members, including Swift symbols whose qualified
   names are mangled.
3. A resolved anchor with no call paths is distinguishable from an absent
   anchor and from a project with no extracted call graph.
4. Trace responses include the repository pagination envelope and never exceed
   the configured page size without `has_more`/`next_offset` metadata.
5. Semantic search collapses Swift getter/setter variants for one logical
   property before applying the requested page, while retaining distinct
   properties and files.
6. `find_references` returns each occurrence object once; source-scope grouping
   remains available through counts or non-duplicating metadata.
7. Existing valid trace, semantic ranking, and reference pagination tests remain
   green.

## Verification plan

Before implementation, add failing unit/contract tests for every criterion.
Then run, in order:

```bash
cd services/palace-mcp
uv run pytest tests/code/test_native_trace_call_path.py \
  tests/code/test_ranking_contract.py \
  tests/code_composite/test_find_references_bundle.py
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest
```

Use targeted `rg` and Serena checks to confirm the final response keys,
pagination call sites, and no unrelated files changed. Live Neo4j verification
is desirable but may be unavailable in this worktree; if unavailable, report
the exact limitation rather than treating mocked unit coverage as production
evidence.

## Adversarial review notes

- The smallest safe trace change is a preflight anchor-resolution query plus
  member expansion; it must not broaden the relationship set.
- Type expansion can multiply paths, so deduplication and pagination must occur
  after member expansion and before response serialization.
- Query-time semantic canonicalization is required because old embeddings may
  already contain Swift accessors; ingestion-only filtering cannot repair them.
- Removing the duplicate grouped occurrence list is a contract change. The
  implementation must preserve counts and explicitly test the chosen metadata
  shape before approval.
- The existing false-success test is a counterexample to preserve as a failing
  regression test until its assertion is changed to the new error contract.

