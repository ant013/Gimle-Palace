# `palace.code.manage_adr` Writable v2 (E5) — Specification

**Document date:** 2026-05-07
**Status:** Draft · **scheduled after Audit-V1 S2.3 completes** (rev4 — CTO-E5-C1 finding)
**Wall-time:** ~2-3w (PE-bound)
**Earliest start:** post-S2.3 merge (week 15+ of 18w AV1 envelope), or post-v1
**Engineer:** Claude PE (same single PE as AV1 critical path; cannot run ‖)
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Claude (Python orchestration; existing manage_adr surface is in `code_router.py` + `mcp_server.py`)
**Slice ID:** Phase 6 E5 (Phase-1-aligned product slice; Claude side)
**Companion plan:** `2026-05-07-palace-code-manage-adr-v2_plan.md`
**Branch:** `feature/GIM-NN-palace-code-manage-adr-v2`

---

## 1. Goal

Promote `palace.code.manage_adr` from read-only / append-only ADR
storage to **writable v2** with full CRUD semantics + provenance
tracking + bridge to `:Decision` graph nodes (per Board memory
`reference_cm_adr_postulate_pattern.md`).

Audit and Board sessions need to:
- Update existing ADR sections without rewriting whole document.
- Mark superseded ADRs with reverse links to the replacement.
- Cross-reference paperclip Decision nodes (post-GIM-95
  `palace.memory.decide` write-tool merger).
- Query "which ADR drove this code change" via git-history-cross-ref.

**Definition of Done:**

1. `palace.code.manage_adr` MCP tool extended to support 4 modes:
   `read` (existing), `write` (new — section-level idempotent
   write), `supersede` (new — mark old as superseded by new),
   `query` (existing — keyword + section filters).
2. `:AdrDocument` + `:AdrSection` Neo4j schema; `:Decision`
   bridge edges (`(d:Decision)-[:CITED_BY]->(a:AdrDocument)`).
3. ADR storage source-of-truth = files in
   `docs/postulates/<slug>.md` (per existing CM ADR pattern); v2
   adds Neo4j projection for graph queries.
4. Bidirectional sync: file edit triggers re-projection; tool write
   produces both file edit AND graph update in single transaction.
5. Operator runbook `docs/runbooks/manage-adr-v2.md`.
6. Smoke: tool can write a new ADR section + supersede an old one
   + query and find both.

## 2. Why now / why this scope

**Now (rev4 — CTO-E5-C1 finding)**: Initial framing claimed "Claude
side has bandwidth, runs ‖ AV1." This is **incorrect** — single
Claude PE is 100% occupied on AV1 chain (S0 → S1 → S2.1 → S2.2 →
S2.3 = 12-14w PE-bound sequential, plus S1.7-S1.10 PE-bound after
S1.6, plus +1w rev4 buffer). E5 has no PE bandwidth in the AV1
envelope.

**Rev4 scheduling**: E5 is **scheduled to start after S2.3 merges**
(approximately week 15 of the 18w envelope). E5 wall-time ~2-3w fits
the remaining envelope tail (week 15 → week 17) before S4 smoke
(week 14, but parallel-with-late-S2 in rev3 critical path) +
S5 scale (week 15-17). Operator may also choose to defer E5 entirely
to post-v1 if other late-stage work crowds it out.

E5 is in Phase 6 backlog (`📦 After Phase 1`); Phase 1 is closed, so
the trigger is satisfied — but PE-bandwidth scheduling within the AV1
envelope governs actual start.

**Scope choice**: write-tool surface intentionally limited to
section-level (not free-text-edit) so the tool can stay idempotent
and Cypher-friendly. Free-text-edit would require diff/merge logic
that's out of scope for v2.

**Why bridge to `:Decision`**: Board memory `reference_cm_adr_postulate_pattern.md`
notes ADR storage already follows the canonical 6-section
PURPOSE/STACK/ARCHITECTURE/PATTERNS/TRADEOFFS/PHILOSOPHY structure.
GIM-95 `palace.memory.decide` writes `:Decision` nodes when an
agent commits to an architectural choice. Edge `:CITED_BY` lets
`palace.audit.run` connect "this finding cites this past decision."

## 3. Scope

### In scope
- **Tool modes**:
  - `read(slug)` → markdown body + section list (existing v1).
  - `write(slug, section, body, run_id?)` → idempotent upsert of a
    named section in the ADR; updates file + graph in same
    transaction.
  - `supersede(old_slug, new_slug, reason)` → marks old as
    superseded; adds reverse link.
  - `query(keyword?, section_filter?, project_filter?)` → existing
    list-search.
- **Schema**:
  - `:AdrDocument {slug, title, status, created_at, updated_at, head_sha}`.
  - `:AdrSection {section_name, body_hash, body_excerpt, last_edit}`.
  - `(:AdrDocument)-[:HAS_SECTION]->(:AdrSection)`.
  - `(:AdrDocument)-[:SUPERSEDED_BY {reason, ts}]->(:AdrDocument)`.
  - `(:Decision)-[:CITED_BY]->(:AdrDocument)` (created via
    `palace.memory.decide` extension).
- **File representation**:
  - Source of truth = `docs/postulates/<slug>.md`.
  - 6-section format (PURPOSE / STACK / ARCHITECTURE / PATTERNS /
    TRADEOFFS / PHILOSOPHY); v2 tool enforces this format on write.

### Out of scope
- Free-text-edit (line-level diff/merge).
- Multi-author conflict resolution beyond last-write-wins on
  section level.
- Auto-supersede inference (operator must call `supersede`
  explicitly).
- Migration of legacy ADR files outside `docs/postulates/` — those
  remain unindexed until manually moved.

## 4. Schema impact

```cypher
(:AdrDocument {
  slug: string,                  // unique key
  title: string,
  status: string,                // "active" | "superseded" | "draft"
  created_at: datetime,
  updated_at: datetime,
  head_sha: string,              // git SHA at last write
  source_path: string            // "docs/postulates/<slug>.md"
})

(:AdrSection {
  section_name: string,          // one of 6 canonical names
  body_hash: string,             // SHA-256 of body content for idempotency
  body_excerpt: string,          // first 500 chars for preview/search
  last_edit: datetime
})

// Edges
(:AdrDocument)-[:HAS_SECTION]->(:AdrSection)
(:AdrDocument)-[:SUPERSEDED_BY {reason, ts}]->(:AdrDocument)
(:Decision)-[:CITED_BY]->(:AdrDocument)
```

Indices:
- `INDEX :AdrDocument(slug)` — primary key.
- `INDEX :AdrDocument(status)` — filter active.
- `INDEX :AdrSection(section_name)` — section filter.

Idempotency: `write(...)` computes `body_hash`; if existing
`AdrSection.body_hash` matches, no-op (return same `run_id`).

## 5. Tool MCP surface

```python
@mcp_tool
async def manage_adr(
    mode: Literal["read", "write", "supersede", "query"],
    slug: str | None = None,
    section: Literal["PURPOSE", "STACK", "ARCHITECTURE", "PATTERNS", "TRADEOFFS", "PHILOSOPHY"] | None = None,
    body: str | None = None,
    old_slug: str | None = None,
    new_slug: str | None = None,
    reason: str | None = None,
    keyword: str | None = None,
    section_filter: str | None = None,
    project_filter: str | None = None,
) -> dict:
    """
    Read/write/query ADR documents.

    Modes:
    - read(slug): full markdown + section list.
    - write(slug, section, body): idempotent upsert.
    - supersede(old_slug, new_slug, reason): mark old as superseded.
    - query(keyword?, section_filter?, project_filter?): list/search.
    """
```

Validation:
- Slug regex `^[a-z][a-z0-9-]*$`.
- Section in canonical 6.
- `write` requires file path under `docs/postulates/` to exist
  OR creates it.

## 6. Decision points

| ID | Question | Default | Impact |
|----|----------|---------|--------|
| **AD-D1** | Source of truth = file or Neo4j? | file (markdown remains canonical) | Neo4j-first = harder to git-diff; loses human review |
| **AD-D2** | `write` mode allows new sections beyond canonical 6? | no — strict (operator extends in v3 if needed) | yes = drift between projects |
| **AD-D3** | `supersede` is one-way only or allows re-revival? | one-way (status → "superseded"; no re-revival) | re-revival = simpler UX but messy graph history |
| **AD-D4** | Cross-project ADR scope or project-scoped? | both (Project ADR has slug like `<project>-<topic>`; cross-project has bare slug) | project-only = easier filter; bare = cross-project intent unclear |
| **AD-D5** | Auto-bridge to `:Decision` (every Decision creates a CITED_BY edge if ADR matches) or manual only? | manual (operator passes `decision_id` arg) | auto = magic; manual = explicit and auditable |

## 7. Test plan

- **Unit**:
  - `read(slug)` reads file, parses 6 sections.
  - `write(slug, section, body)` idempotent; same content twice =
    same `body_hash`.
  - `supersede(old, new, reason)` creates correct `:SUPERSEDED_BY`
    edge.
  - `query(keyword)` finds matching sections.
- **Integration** (testcontainers Neo4j + tmp dir):
  - Write a new ADR file from scratch via tool; assert file +
    graph match.
  - Edit an existing ADR via tool; assert old `:AdrSection` body_hash
    replaced.
  - Supersede ADR; assert old `status="superseded"`, new
    `status="active"`, edge present.
  - Query by keyword across multiple ADRs.
- **Smoke**: real ADR file under `docs/postulates/` (e.g.,
  `gimle-purpose.md`) — extract sections via tool, verify graph
  reflects file.

## 8. Risks

- **R1 — file/graph drift**: file edited outside the tool (e.g., manual
  `vim`), graph stale. Mitigation: extractor provides `manage_adr.sync`
  subcommand that re-projects file→graph; runbook recommends running
  it after manual edits.
- **R2 — section name typos**: write fails on unknown section. Mitigation:
  Pydantic Literal type catches at MCP boundary; tool returns clear
  error envelope.
- **R3 — concurrent writes**: two agents write same section
  simultaneously. Mitigation: file-level `flock`; second writer
  retries after delay; document in runbook.
- **R4 — git tracking churn**: every `write` produces a file change;
  PRs accumulate noise. Mitigation: agents batch writes; commit at
  end of slice rather than per call.

## 9. Out of scope

- ADR templating / scaffolding (operator authors initial file).
- ADR review workflow (e.g., paperclip ADR-review issues).
- Cross-instance sync (Medic <-> Gimle ADR cross-reference).
- Auto-supersede heuristics.

## 10. Cross-references

- Memory: `reference_cm_adr_postulate_pattern.md` — canonical 6-section
  format.
- Predecessor (read-only v1): existing manage_adr in `code_router.py`.
- Sibling: GIM-95 `palace.memory.decide` write tool (`a82c549`).
- Roadmap: `docs/roadmap-archive.md` §"Phase 6" E5 row.
- Audit-V1 integration: `:CITED_BY` edges may surface in audit
  report §1 Architecture as "decision provenance" — post-v1
  enrichment.
- Companion: `2026-05-07-palace-code-manage-adr-v2_plan.md`.
