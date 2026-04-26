# Plan: GIM-100 — Multi-language foundation research

**Issue:** GIM-100
**Type:** Research (no implementation)
**Branch:** `feature/research-multi-language-foundation`
**Output:** `docs/superpowers/research/2026-04-27-multi-language-foundation-design.md`

---

## Phase 2 — ResearchAgent execution

**Owner:** ResearchAgent (`0083815d-78fa-4646-bc2d-fa6a9c10c25c`)

### Task 2.1 — Q1: Cross-language FQN unification

**Description:** Research and propose canonical FQN format for 9 languages.

**Acceptance criteria:**
- Per-language native FQN format documented (Python, Kotlin, Swift, Rust, Solidity, FunC, Anchor/Solana, JS, TS)
- Semantic-index tool outputs compared (SCIP, tree-sitter scope-graphs, LSP)
- Special cases catalogued (generics, lambdas, nested types, trait impls, extensions, macros)
- Canonical `qualified_name` format proposed with rationale
- Cross-language linkage strategy (SKIE bridge, Anchor↔JS, etc.)
- Every claim has `[HIGH/MEDIUM/LOW/SPECULATIVE]` tag
- Source tier discipline: official docs > library source > maintainer blog > forum
- Version-pinned claims (e.g. "SCIP 0.3.x uses...")
- `[MATERIAL GAP]` flags for FunC/Anchor where sources are sparse

**Affected files:** `docs/superpowers/research/2026-04-27-multi-language-foundation-design.md` §Q1

**Dependencies:** None (parallel-safe with Q2, Q3)

### Task 2.2 — Q2: SymbolOccurrence storage scale & strategy

**Description:** Benchmark and recommend storage strategy for 30-70M occurrence records.

**Acceptance criteria:**
- Neo4j 5.26 empirical scale data cited (insertion throughput, query latency, storage, memory)
- Tantivy/Lucene benchmarks for code-index workloads cited (Zoekt, Gitlab Elastic)
- Tradeoff matrix scoring options A/B/C/D on 6 dimensions
- Recommendation with rationale
- All benchmarks from cited sources (no invented numbers)
- `[HIGH/MEDIUM/LOW/SPECULATIVE]` tags per finding
- `[MATERIAL GAP]` where Neo4j-at-scale benchmarks are unavailable for code workloads specifically

**Affected files:** `docs/superpowers/research/2026-04-27-multi-language-foundation-design.md` §Q2

**Dependencies:** None (parallel-safe with Q1, Q3)

### Task 2.3 — Q3: Unified ExternalDependency schema

**Description:** Survey 9 ecosystem manifests and propose canonical `:ExternalDependency` node schema.

**Acceptance criteria:**
- Per-ecosystem manifest survey (file format, identifier, version syntax, registry, resolution model)
- Conflict/overlap analysis (cross-ecosystem name collisions, lockfile precedence, vendored deps)
- Canonical schema proposal: node properties + edges + ecosystem discriminator
- Cross-extractor coordination strategy (who creates, who enriches, idempotency)
- `[HIGH/MEDIUM/LOW/SPECULATIVE]` tags
- `[MATERIAL GAP]` flags for FunC/TON/Tact

**Affected files:** `docs/superpowers/research/2026-04-27-multi-language-foundation-design.md` §Q3

**Dependencies:** None (parallel-safe with Q1, Q2)

### Task 2.4 — Report assembly & self-check

**Description:** Assemble sections into single report, add executive summary, top-3 recommendations, follow-up questions, recency window statement.

**Acceptance criteria:**
- Single file at the specified path
- Top-3 recommendations ranked by decision impact
- Follow-up questions for unanswered axes
- Recency window stated explicitly
- All 9 acceptance criteria from issue body satisfied
- Git push to `feature/research-multi-language-foundation`

**Affected files:** `docs/superpowers/research/2026-04-27-multi-language-foundation-design.md`

**Dependencies:** Tasks 2.1, 2.2, 2.3 complete

---

## Phase 3.1 — CodeReviewer mechanical review

**Owner:** CodeReviewer

### Review checklist:
- [ ] Every factual claim has a citation (URL + date)
- [ ] `[HIGH/MEDIUM/LOW/SPECULATIVE]` tags present on all findings
- [ ] Source tier discipline followed (official > source > blog > forum)
- [ ] Library version pinned on every library claim
- [ ] `[MATERIAL GAP]` flags where research is genuinely sparse
- [ ] `[VERSION GAP]` flags where cited version may not reflect current
- [ ] No training-cutoff inferences masquerading as current facts
- [ ] Schema proposals are concrete (property names, types, constraints) not vague
- [ ] Cross-references between Q1/Q2/Q3 schemas are consistent

**Output:** APPROVE or REQUEST CHANGES with specific items

---

## Phase 3.2 — OpusArchitectReviewer adversarial review

**Owner:** OpusArchitectReviewer

### Adversarial categories:
- **Missing perspectives:** Are there ecosystems, edge cases, or scale scenarios not covered?
- **Unfounded claims:** Any recommendation not supported by cited evidence?
- **Schema contradictions:** Do Q1/Q2/Q3 proposals conflict with each other? (e.g. Q1 FQN format incompatible with Q3 dependency resolution)
- **Scale assumptions:** Are Q2 benchmarks relevant to our actual workload profile?
- **Cross-language gaps:** Does the FQN unification handle bridge cases (SKIE, JNI, WASM, IDL) or hand-wave?
- **Operational feasibility:** Is the recommended architecture deployable on iMac-class hardware?

**Output:** APPROVE or REQUEST CHANGES with specific adversarial findings

---

## Phase 5 — Board ratification (STOP gate)

**Owner:** Board (manual)

After Opus APPROVE, issue status → `in_review` assigned to Board. Board ratifies schemas via `palace.memory.decide` per canonical decision process. No implementation slice opens until Board approves.

---

## Iteration limit

2 review iterations max. If CR or Opus cannot APPROVE after 2 rounds → escalate `@Board` with `[BLOCKED]`.

## Notes

- Tasks 2.1/2.2/2.3 are parallel-safe — ResearchAgent may use sub-agents for each
- No code is produced in this slice — output is markdown only
- ResearchAgent should NOT read parallel Board-side voltagent research (independence constraint)
