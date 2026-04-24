---
slug: N1-decomposition
status: proposed
branch: feature/GIM-74-n1a-graphiti-cm-foundation
paperclip_issue: 74 (umbrella, 90c9af9e-ee37-4d98-9cb5-2041fb364b87)
sub_issues:
  - GIM-75 (0855b069-3e42-4cc8-b644-6dec26660111) — Graphiti foundation
  - GIM-76 (9917ad4d-102f-4c81-afcd-22a9a6c71881) — Codebase-Memory sidecar
  - GIM-77 (b7198de1-b3d9-469c-a5d9-86c1badb3aaf) — Bridge extractor
predecessor: 67d42dc (develop tip)
date: 2026-04-24
---

# N+1 Decomposition — three atomic sub-slices for the Graphiti + Codebase-Memory foundation

## Why this document exists

Original combined spec `2026-04-24-N1a-graphiti-codebase-memory-foundation-design.md` failed operator review on five grounds (schema inconsistency, unverified Graphiti runtime, ADR split-brain, untestable assertions, and mega-slice scope). Rather than patch in place, the scope was split into three atomic sub-slices, each independently mergeable and reviewable. This document is the coordination/tracking artifact — it does not itself specify implementation; the three sub-specs do.

## The three sub-slices

### GIM-75 — N+1a.1 Graphiti foundation (storage swap only)

**File:** `docs/superpowers/specs/2026-04-24-N1a-1-graphiti-foundation-design.md`

Embed `graphiti-core==0.28.2` in `palace-mcp`. Define Pydantic entity and edge catalog. Add `ensure_graphiti_schema()` bootstrap. Refactor `BaseExtractor` to accept a `graphiti: Graphiti` ctx. Refactor `heartbeat` extractor to write `:Episode` via `add_triplet`. Remove the N+0 paperclip test extractor.

**No sidecar, no bridge.** This slice is purely about wiring Graphiti into the existing `palace-mcp` process and replacing the raw-Neo4j extractor base with a Graphiti-aware one.

**Estimate:** 500–700 LOC. **Parallelizable with GIM-76.**

### GIM-76 — N+1a.2 Codebase-Memory sidecar (pass-through only)

**File:** `docs/superpowers/specs/2026-04-24-N1a-2-codebase-memory-sidecar-design.md`

Add `codebase-memory-mcp` (MIT) as a sidecar service via docker-compose `code-graph` profile. Implement `palace.code.*` router in `palace-mcp` that forwards to the sidecar. Explicitly disable `palace.code.manage_adr` in the router (reserved for a future sync slice if needed).

**No Graphiti projection.** This slice is purely about standing up the code-layer MCP endpoint and exposing it through the palace-mcp surface.

**Estimate:** 400–500 LOC. **Parallelizable with GIM-75.**

### GIM-77 — N+1a.3 Bridge extractor (depends on GIM-75 + GIM-76)

**File:** `docs/superpowers/specs/2026-04-24-N1a-3-bridge-extractor-design.md`

New extractor `codebase_memory_bridge` that reads from the CM sidecar via `palace.code.*` and projects selected facts (`:File`, `:Symbol{kind=...}`, `:Module`, `:APIEndpoint`, `ArchitectureCommunity`, `Hotspot`) into Graphiti with metadata envelope (`confidence`, `provenance`, `extractor`, `cm_id`, `observed_at`) and Graphiti-native bi-temporal edges.

**Depends on both previous slices merging first.**

**Estimate:** 500–700 LOC.

## Ordering / dependency graph

```
GIM-75 ──┐
         ├──► GIM-77
GIM-76 ──┘
```

GIM-75 and GIM-76 can proceed in parallel after GIM-74 umbrella spec merges. GIM-77 cuts a branch from `develop` only after both merge.

## Cross-cutting decisions (apply to all three sub-slices)

- **`graphiti-core==0.28.2`** verified live 2026-04-24 via isolated-venv spike. See `memory/reference_graphiti_core_0_28_api_truth.md`.
- **LLM client trap:** pass `OpenAIClient(api_key=$OPENAI_API_KEY)` to `Graphiti(...)` as a stub. Writes go through `add_triplet` — LLM call never fires. Passing `None` creates an OpenAI default client that errors on missing key at construction time.
- **Metadata envelope** — `confidence`, `provenance` (`asserted` / `derived` / `inferred`), `extractor`, `extractor_version`, `evidence_ref`, `observed_at` — stored in `EntityNode.attributes: dict` and `EntityEdge.attributes: dict`. **No Pydantic subclassing needed** in 0.28.
- **Schema is flat:** `:Symbol{kind=function|method|class|interface|enum|type}` in Graphiti. Separate `:Class/:Method/:Package/:Folder` labels are not replicated — those live in CM SQLite. Query Graphiti by `(n:Symbol {kind: "class"})`, not by label.
- **Domain-concept axis is multi-label, not node.** `:Symbol` carries labels like `[Symbol, HandlesHex, Encodes]`. No standalone `:DomainConcept` node. Edges that the old §5 wrote as `:APPLIES_TO -> :DomainConcept` become `:APPLIES_TO -> :Symbol` with a label filter on the target.
- **CM's `manage_adr` disabled.** Graphiti `:Decision` is the single source of truth for architectural decisions. The router in GIM-76 explicitly rejects `palace.code.manage_adr` with an error directive.
- **Embedder:** OpenAI `text-embedding-3-small` (pre-paid credit, $11.20 covers decades at projected volume).

## What this umbrella doc does NOT decide

- Per-slice task breakdown — lives in each sub-spec.
- Unit/integration test catalogs — per sub-spec.
- Acceptance gates — per sub-spec.
- Risk list — umbrella-level risks only; per-slice risks per sub-spec.

## Umbrella-level risks

| Risk | Mitigation |
|---|---|
| GIM-75 or GIM-76 drifts in scope and blocks the other | Strict written boundaries in each sub-spec; operator reviews each before handoff to CTO. |
| Contract between GIM-75 (BaseExtractor signature) and GIM-77 (bridge implements it) drifts | GIM-75 defines the `BaseExtractor` + Graphiti ctx signature. GIM-77 spec references the GIM-75 signature explicitly. Re-verify before GIM-77 Phase 1.1. |
| Contract between GIM-76 (`palace.code.*` routing) and GIM-77 (bridge consumes `palace.code.*`) drifts | GIM-76 documents the exact 7 tools exposed + `manage_adr` disabled. GIM-77 consumes only those. Re-verify before GIM-77 Phase 1.1. |
| Sub-issues pile up if GIM-77 blocks for weeks waiting for GIM-75 and GIM-76 | GIM-75 and GIM-76 are both sized for ≤ 1 week under normal paperclip-team cadence. Operator enforces single-slice-at-a-time on each agent. |
| Combined value unclear until all three land — N+1a.1 and .2 individually are not user-visible | Accept — this is the cost of atomic slicing. N+1a.1 proves Graphiti works (heartbeat `:Episode`); N+1a.2 proves CM works (`palace.code.*` live); N+1a.3 connects them. |

## References

- Paperclip issues: GIM-74 (umbrella), GIM-75, GIM-76, GIM-77.
- Sub-specs (same commit): `2026-04-24-N1a-1-graphiti-foundation-design.md`, `2026-04-24-N1a-2-codebase-memory-sidecar-design.md`, `2026-04-24-N1a-3-bridge-extractor-design.md`.
- Deprecated combined spec (historical): `2026-04-24-N1a-graphiti-codebase-memory-foundation-design.md`.
- Graphiti 0.28.2 verified API: `memory/reference_graphiti_core_0_28_api_truth.md`.
- Predecessor merge: `67d42dc` (develop tip at design time).
- Research basis: `docs/research/agent-context-store-2026-04/`.
- Operator review feedback (in-session 2026-04-24) — five flagged issues addressed above.
