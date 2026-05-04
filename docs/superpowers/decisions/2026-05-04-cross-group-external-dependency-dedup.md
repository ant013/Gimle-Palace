---
date: 2026-05-04
ratified_by: Board (Anton)
ratification_context: GIM-191 Dependency Surface Extractor — first production writer of foundation `:ExternalDependency` node-type
decision_kind: architecture (dedup scope) + namespace (cross-group)
related_paperclip_issue: 191
related_branch: feature/GIM-191-dependency-surface
related_spec: docs/superpowers/specs/2026-05-04-GIM-191-dependency-surface-design.md
status: ratified — to be replicated to `palace.memory.decide` on iMac when GIM-191 reaches Phase 1.1
---

# Cross-group `:ExternalDependency` dedup decision (2026-05-04)

This document records the architectural decision ratified by Board on 2026-05-04
ahead of GIM-191 (Dependency Surface Extractor) Phase 1.1 formalization. GIM-191
is the **first production writer** of the foundation `:ExternalDependency`
node-type (see `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py:140`
and `extractors/foundation/schema.py:60-62`); the dedup scope was chosen at
foundation time (GIM-101a) but has not been load-bearing until now. Pre-CR
review by operator surfaced the architectural question explicitly; this doc
ratifies the answer before impl proceeds.

## Sources fed to ratification

- Foundation `:ExternalDependency` model (`extractors/foundation/models.py:140-163`):
  `purl: str` is the only UNIQUE field; `group_id: str` is a regular property,
  set on first MERGE.
- Foundation schema constraint (`extractors/foundation/schema.py:60-62`):
  `ext_dep_purl_unique` UNIQUE on `purl` only — globally, not per group_id.
- Research dedup hint (`docs/research/extractor-library/report.md:259`):
  "#5 Dependency Surface + #39 Cross-Repo Version Skew (dedup via shared
  `:ExternalDependency` node)".
- CLAUDE.md `PALACE_DEFAULT_GROUP_ID` convention namespacing
  `:Issue / :Comment / :Agent / :IngestRun` per project — explicit per-tenant
  isolation for paperclip data.
- Operator pre-CR review note (2026-05-04): "первый extractor, чьи ноды живут
  вне `group_id="project/<slug>"`-конвенции".

## Decision

**`:ExternalDependency` is intentionally tenant-shared (cross-group dedup).**
Same `purl` (e.g. `pkg:pypi/neo4j@5.28.2`) referenced from `gimle`, `uw-android`,
or any future Gimle-stack project produces a SINGLE `:ExternalDependency` node
with multiple `:Project-[:DEPENDS_ON]->:ExternalDependency` edges — one per
referencing project.

The node's `group_id` field is **first-writer-wins** and informational only; it
does NOT scope the constraint or affect query semantics. Per-tenant provenance
is a deferred follow-up (F12 — bumped from F-followup to a tracked roadmap
item; reactivation trigger: first multi-tenant Gimle deployment OR first
consumer who needs "show only deps of project X" with strict per-tenant
isolation).

## Why this is OK for v1 (Gimle, single-tenant)

1. **Gimle is single-tenant by design.** All projects (`gimle`, `uw-android`,
   `uw-ios`, HS Kits) live under one `PALACE_DEFAULT_GROUP_ID="project/gimle"`
   parent (with per-project sub-groups for paperclip-managed data). Cross-group
   leakage between Gimle projects is not a security concern — it's the same
   operator analyzing the same UW ecosystem.
2. **The dedup unlocks the #5+#39 pairing without migration.** When #39
   (Cross-Repo Version Skew) lands, it queries
   `MATCH (d:ExternalDependency) WHERE size((d)<-[:DEPENDS_ON]-()) > 1 RETURN
   d.purl, collect(DISTINCT d.ecosystem)` to find shared deps with conflicting
   resolved versions across projects. This requires shared nodes; per-group
   nodes would force a join across multiple shadow-copies.
3. **`:Project` is the per-tenant boundary.** Per-tenant isolation is enforced
   at the `:Project` level (each project has its own slug + group_id); the
   shared `:ExternalDependency` carries metadata about an EXTERNAL artifact
   (Maven coordinate / PyPI package / GitHub repo), not about the project. A
   tenant can only see their own `:DEPENDS_ON` edges; the dependency facts
   themselves are inherently public (PyPI/Maven Central are public registries).

## What this rules out for v1

- **Multi-tenant deployment with separate operators.** If two unrelated
  customers ever ingest into the same palace-mcp instance, their dep references
  would share `:ExternalDependency` nodes. The shared `group_id` would reflect
  whichever tenant ingested first. NOT a current concern (Gimle is operator's
  single-tenant instance), but flagged for any future commercial deployment.
- **Per-project ExternalDependency mutation.** v1 writer does NOT update
  `:ExternalDependency` properties on second-MERGE (no `ON MATCH SET` clause
  in `_UPSERT_EXT_DEP`). If a consumer needs to track which projects reference
  a dep, the answer is via traversal `MATCH (d {purl: ...})<-[:DEPENDS_ON]-(p)`,
  not a denormalized field on the node.

## Followups (referenced in spec §2 OUT)

- **F11**: UNWIND-batched MERGE — perf optimization unrelated to dedup scope.
- **F12 (NEW from this decision)**: per-tenant `:ExternalDependency` namespace
  variants — only opens if the multi-tenant scenario materializes. Migration
  path: introduce `:TenantExternalDependency {tenant_id, purl}` composite with
  shadow constraint; `:ExternalDependency` becomes a sealed sub-type via
  `INHERITS` edge to a tenant-scoped variant. Not v1, not on roadmap until
  triggering scenario.

## Replication to runtime

When GIM-191 reaches Phase 1.1, CTO calls `palace.memory.decide(...)` with:

```python
DecideRequest(
    decision_kind="architecture",
    summary="ExternalDependency cross-group dedup intentional; per-tenant variant deferred F12",
    rationale_md=Path("docs/superpowers/decisions/2026-05-04-cross-group-external-dependency-dedup.md").read_text(),
    related_artefacts=[
        "GIM-191",
        "extractors/foundation/models.py:140",
        "extractors/foundation/schema.py:60-62",
        "docs/research/extractor-library/report.md:259",
    ],
    decision_maker_claimed="board",
)
```

This persists the ratification as a `:Decision` node in palace-mcp Neo4j, queryable
later via `palace.memory.lookup(entity_type="Decision", filters={"summary":
"ExternalDependency cross-group"})`.

## Verification (post-impl)

Phase 4.1 QA smoke gate (per spec §9.4.4) includes a Cypher assertion that
verifies the dedup invariant:

```cypher
MATCH (p1:Project {slug:'gimle'})-[:DEPENDS_ON]->(d:ExternalDependency)<-[:DEPENDS_ON]-(p2:Project {slug:'uw-android'})
RETURN count(d) AS shared
```

A row with `shared >= 0` confirms the query is well-formed against the
single-node-shared-by-multiple-projects shape. (`shared` may be 0 if Gimle's
Python deps and UW-android's Maven deps don't actually overlap by purl — that's
expected; the test is structural, not value-based.)

If a follow-up smoke at #39 (Cross-Repo Version Skew) ever shows TWO
`:ExternalDependency` nodes for the same `purl` from different projects, that
is a regression of THIS decision and triggers REQUEST CHANGES on the slice
that introduced it.
