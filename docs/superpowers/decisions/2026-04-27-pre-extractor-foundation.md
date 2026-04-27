---
date: 2026-04-27
ratified_by: Board (Anton)
ratification_context: GIM-100 multi-language foundation research + voltagent independent track + memory-bounded research
decision_kind: design (× 9)
related_paperclip_issue: 100
related_branch: feature/extractor-symbol-index-foundation
status: ratified — to be replicated to palace.memory.decide on iMac
---

# Pre-extractor foundation decisions (2026-04-27)

This document records the 9 architectural decisions ratified by Board on 2026-04-27, gating the implementation of `:SymbolOccurrence` extractor (#21 from the 45-item roadmap) and all subsequent extractors. Each decision is intended to be replicated to Graphiti `:Decision` nodes via `palace.memory.decide` on the iMac docker stack as part of the implementation slice's Phase 1.1 (CTO formalize step).

## Sources fed to ratification

- ResearchAgent autonomous output: `feature/research-multi-language-foundation/docs/superpowers/research/2026-04-27-multi-language-foundation-design.md` (commit `3d5b5db`, GIM-100)
- CR Phase 3.1 review (APPROVE on iteration 1 re-review)
- Opus Phase 3.2 adversarial review (NUDGE — 5 architectural findings, 3 minor)
- Voltagent independent cross-check tracks:
  - `/tmp/voltagent_research/q2_scale_findings.md` — Hybrid Tantivy+Neo4j recommendation
  - `/tmp/voltagent_research/q3_dependencies_findings.md` — PURL ECMA-427 unified schema
  - `/tmp/voltagent_research/memory_bounded_index_findings.md` — importance + tiers + eviction
- Operator's stated multi-language stack: `~/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory/project_tech_stack.md`
- Operator's research-first global preference: `~/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory/feedback_research_first_global.md`

## Decisions

### D1 — FQN canonical format = SCIP-aligned grammar

**Body:** All `:SymbolOccurrence` and `:Symbol` nodes store `qualified_name` using SCIP's symbol grammar verbatim where SCIP indexers exist (Python, JavaScript, TypeScript, Kotlin, Java, partial Rust). For languages without SCIP indexers (Swift, Solidity, FunC, Anchor), use `palace` as scheme with SCIP-compatible custom symbol generators. SCIP grammar: `<scheme> ' ' <package> ' ' (<descriptor>)+` where `<package> ::= <manager> ' ' <package-name> ' ' <version>`.

**Rationale:** SCIP is battle-tested at Sourcegraph across 10+ languages, adopted by Mozilla Searchfox and Meta Glean. Choosing a custom format = building all tooling from scratch. Choosing SCIP = leverage existing indexers for 6/9 languages.

**Confidence:** HIGH (ResearchAgent + voltagent converge with minor format difference; SCIP is industry-standard).

**Evidence ref:**
- ResearchAgent report §Q1 (commit `3d5b5db`)
- voltagent Q1 transcript (33 sources)
- SCIP proto: github.com/sourcegraph/scip/blob/main/scip.proto

**Decision_kind:** design
**Decision_maker_claimed:** board

### D2 — `:SymbolOccurrence` storage = Hybrid (Tantivy sidecar + Neo4j)

**Body:** Storage architecture splits at `:Symbol` node boundary. Neo4j retains semantic relationships: `:Symbol` definitions, `[:CALLS]`, `[:TESTS]`, `[:IMPLEMENTS]`, `[:BRIDGES_TO]` edges, cross-repo links. Tantivy (Rust-based inverted index) holds dense positional `:SymbolOccurrence` records with fields: `symbol_id` (fast), `repo_id` (fast), `file_path` (text), `line` (range), `col_start`, `col_end` (fast), `role` (def/ref/impl), `language`, `commit_sha`, `importance` (fast). Bridge layer routes queries: Neo4j for "go to definition" / cross-repo traversal; Tantivy for "find all references" / occurrence aggregation.

**Rationale:** Neo4j Block format = ~128 B per node minimum; 50M occurrences alone require 25-100 GB store + 36-40 GB page cache. Critically, popular symbols (>100K occurrences) hit Neo4j's **supernode problem** — O(degree) traversal for "find all references" — which is structural and not tunable via indexing. Tantivy's inverted index = ms-level lookup at 50M+ records, ~4-6 GB on disk compressed. Embedded via tantivy-py FFI (no separate service required).

**Confidence:** HIGH (voltagent + Opus Finding 3 reinforce; Sourcegraph Zoekt + GitHub Blackbird precedent).

**Evidence ref:**
- voltagent Q2 findings (`/tmp/voltagent_research/q2_scale_findings.md`)
- Opus Phase 3.2 Finding 3 (memory estimate omits index overhead)
- Sourcegraph Zoekt: 2.6B lines / 166 GB at 1.2× corpus RAM
- Tantivy 0.22 benchmarks

**Decision_kind:** design
**Decision_maker_claimed:** board

### D3 — `:ExternalDependency` schema = single label + ecosystem discriminator + PURL identity

**Body:** All third-party dependencies modeled as `:ExternalDependency` nodes with PURL (Package URL, ECMA-427 December 2025) as universal canonical key. Format: `pkg:<type>/<namespace>/<name>@<version>`. Composite Neo4j unique constraint on `(ecosystem, canonical_name, resolved_version)`. Version constraint (manifest-declared, e.g., `^1.2.3`) lives on `[:USES]` edge property; resolved version (lockfile-truth, e.g., `1.4.7`) lives on the node. `source_type` enum: `registry | git | path | vendor | binary` covers Foundry git-submodule and FunC vendor-copy edge cases. Per-ecosystem normalized name (PEP 503 for pypi, lowercase for npm, group:artifact for maven).

**Rationale:** PURL is finalized international standard (ECMA-427) covering all 9 ecosystems in operator's stack. Composite key pattern is what every major SBOM standard uses (CycloneDX, SPDX). Cross-ecosystem queries work without UNION clauses. Adding 10th ecosystem requires no schema migration. Per Opus Finding 1, prefer Neo4j composite constraint over sha256 hash for debuggability.

**Confidence:** HIGH (voltagent + ResearchAgent converge on schema shape; Opus refines uniqueness constraint).

**Evidence ref:**
- voltagent Q3 findings (`/tmp/voltagent_research/q3_dependencies_findings.md`)
- ResearchAgent report §Q3 (commit `3d5b5db`)
- Opus Phase 3.2 Findings 1, 2 (composite constraint, RESOLVES_TO edge correlation)
- ECMA-427: ecma-international.org/wp-content/uploads/ECMA-427_1st_edition_december_2025.pdf

**Decision_kind:** design
**Decision_maker_claimed:** board

### D4 — Memory-bounded importance score on every `:SymbolOccurrence`

**Body:** Each `:SymbolOccurrence` carries an `importance` float in [0, 1] computed at ingest time:

```
importance = clamp(
    0.35 × log1p(cms_in_degree) / log1p(100)   // centrality, CMS-approximated
  + 0.30 × tier_weight                          // 1.0 user / 0.5 first-party / 0.1 vendor/stdlib
  + 0.20 × kind_weight                          // def=1.0, decl=0.8, assign=0.5, use=0.3
  + 0.10 × exp(-days_since_last_seen / 30.0)   // recency half-life 30d
  + 0.05 × language_weight                      // primary lang=1.0, others=0.7
, 0.0, 1.0)
```

In-degree approximated via in-process Count-Min Sketch (~2 MB RAM, O(1) per write); covers 70M distinct symbols at 1% relative error. Tier weight derived from file path against vendor regex (`node_modules/`, `vendor/`, `.cargo/registry/`, `site-packages/`, `Pods/`, `__pycache__/`, etc.). Periodic background reconciliation via Neo4j GDS PageRank (weekly).

**Rationale:** Score serves as eviction priority and at-ingest filter. CMS in-degree correlates strongly with PageRank for sparse symbol reference graphs but is computable in O(1) per write vs O(V+E) × 20 iterations. Pre-computed score on each node is the structural equivalent of cache "visited bit" but persists across DB restarts.

**Confidence:** MEDIUM-HIGH (memory-bounded research synthesis; CMS-vs-PageRank correlation needs prototype validation).

**Evidence ref:**
- voltagent memory-bounded findings (`/tmp/voltagent_research/memory_bounded_index_findings.md`)
- Sourcegraph "Ranking in a Week" (PageRank undirected)
- Count-Min Sketch (Cormode & Muthukrishnan)

**Decision_kind:** design
**Decision_maker_claimed:** board

### D5 — Tier-aware deployment defaults (4-tier table)

**Body:** Configurable via env vars; defaults encode operator's deployment profile.

| Machine | Data budget | `PALACE_MAX_OCCURRENCES_TOTAL` | `PALACE_IMPORTANCE_THRESHOLD_USE` | Coverage |
|---|---|---|---|---|
| 8 GB VPS | ~3 GB | 5,000,000 | 0.35 | Defs + critical uses only |
| 16 GB MacBook | ~7 GB | 15,000,000 | 0.20 | Defs + most user uses |
| 32 GB workstation | ~18 GB | 30,000,000 | 0.10 | Near-full user coverage |
| **64 GB iMac (32 GB ceiling)** | **~28 GB** | **50,000,000** | **0.05** | Full user; vendor sampled |

**Rationale:** iMac 32 GB ceiling is operational constraint — remaining 32 GB reserved for paperclip agents (12 of them) + Claude Code processes + OS. Calibration: at 200 B/Tantivy doc + Neo4j Block format ~128 B/node + index overhead 1.2×, 50M occurrences fits in ~28 GB total. Tantivy compresses 5-10× vs Neo4j Block format, freeing iMac headroom.

**Confidence:** HIGH for math; MEDIUM for actual occurrence count per language (needs validation on real Eip20Kit.Swift index).

**Evidence ref:**
- Operator constraint statement 2026-04-27: "iMac 64GB но max 32GB под данные — иначе мы не сможем держать саму команду"
- Memory-bounded research §Configuration patterns

**Decision_kind:** design
**Decision_maker_claimed:** board

### D6 — 3-phase bootstrap on fresh installs

**Body:** Initial ingestion proceeds in three phases, conditional on remaining budget.

1. **Phase 1 (always, no threshold):** Index only `kind=def` and `kind=decl`. 5-10% of total occurrence volume but 100% of navigation targets. Completes in minutes; index immediately useful for "go to definition."
2. **Phase 2 (if budget < 50% used after Phase 1):** Ingest user-code `kind=use` occurrences (tier_weight = 1.0) with `IMPORTANCE_THRESHOLD_USE` filter. Largest query-quality jump occurs here.
3. **Phase 3 (only on machines with budget remaining after Phase 2):** Vendor/stdlib uses above importance threshold. Skip on 8 GB and 16 GB tiers.

**Rationale:** Phase 1 guarantees baseline functionality on any machine. Phases 2 and 3 are progressive enrichment. Fail-safe: a small machine running out of budget mid-Phase-2 still has a fully usable index from Phase 1.

**Confidence:** HIGH (matches Cursor / Plandex conventional vendor-exclusion pattern; novel phasing is straightforward).

**Evidence ref:**
- voltagent memory-bounded findings §Section 3 (tiered indexing)

**Decision_kind:** design
**Decision_maker_claimed:** board

### D7 — Eviction policy = 3-round Cypher pruning, never auto-evict definitions

**Body:** Triggered when `MATCH (o:SymbolOccurrence) RETURN count(o)` exceeds `PALACE_MAX_OCCURRENCES_TOTAL`. Soft threshold (90%): pause new low-importance ingestion; log warning. Hard threshold (100%): run pruning Cypher in batches of 100K:

- Round 1: vendor/stdlib uses (`importance < 0.2 AND kind = 'use' AND tier_weight ≤ 0.1`)
- Round 2: inactive user uses (`importance < 0.4 AND kind = 'use' AND last_seen_at < datetime() - duration({days: 90})`)
- Round 3 (if still over): assign records (`importance < 0.3 AND kind = 'assign'`)

**NEVER auto-evict `kind=def` or `kind=decl`** (navigation targets). Each evicted batch records `:EvictionRecord {symbol_fqn, evicted_at, count_evicted}` for query-time warnings.

**Rationale:** Definitions are irreplaceable navigation anchors; usage occurrences can be regenerated by re-running the extractor. Eviction order minimises navigation regression.

**Confidence:** HIGH for ordering principle; MEDIUM for specific thresholds (operator may tune 0.2/0.4/0.3 cutoffs based on production feedback).

**Evidence ref:**
- voltagent memory-bounded findings §Section 6 (recommended approach)

**Decision_kind:** design
**Decision_maker_claimed:** board

### D8 — Graceful degradation: never silent-empty queries

**Body:** When a query result touches symbols with `:EvictionRecord` entries, the response includes a structured warning:

```json
{
  "ok": true,
  "tests": [...],
  "total_found": 47,
  "warning": "partial_index",
  "eviction_note": "12 occurrences evicted on 2026-04-27; coverage may be incomplete for this symbol",
  "coverage_pct": 79
}
```

Caller can fallback to Serena LSP (Python/JS/TS/Kotlin/Swift/Rust covered) or accept partial. Failure mode is explicit; never silent. Hard circuit breaker: extractor aborts ingestion with `error_code: budget_exceeded` if live count exceeds 1.1 × max during a single run.

**Rationale:** Silent empty results are the worst failure mode — caller cannot distinguish "no occurrences" from "occurrences evicted." Explicit warning matches Google Cloud / AWS Well-Architected graceful-degradation pattern.

**Confidence:** HIGH.

**Evidence ref:**
- voltagent memory-bounded findings §Section 6.4 (failure modes)
- Google Cloud "Design for graceful degradation"

**Decision_kind:** design
**Decision_maker_claimed:** board

### D9 — Serena complementary scope; extractor #21 does not duplicate LSP

**Body:** Extractor #21 (and subsequent symbol/occurrence extractors) does NOT replicate what Serena LSP integration already covers for interactive lookups in Python, JavaScript, TypeScript, Kotlin, Swift, Rust. Extractor #21 focus:

- **Smart contract languages** (Solidity / FunC / Anchor — no production LSP) — full coverage
- **Cross-language bridges** (SKIE Swift↔Kotlin, JS↔Solana IDL, Rust↔Anchor `declare_id!`) — modeled as `:BRIDGES_TO` edges
- **Persistent metrics** (churn × occurrence-count for hotspot detection, cross-project aggregates) — not Serena's job
- **Mainstream languages** (Python/JS/TS/Kotlin/Swift/Rust) — sampled occurrence indexing for aggregate queries; full granularity NOT required since Serena handles point lookups

**Rationale:** Serena via LSP provides real-time, accurate, language-server-quality results for interactive "find references" / "go to definition" on covered languages. Duplicating this in our index = wasted RAM. Reduces extractor #21 storage scope by an estimated 2-3×.

**Confidence:** HIGH (Serena coverage well-documented; smart contract LSP gap confirmed in Q1 research).

**Evidence ref:**
- Serena Module documentation (LSP-based, multi-language)
- voltagent Q1 findings §FunC, §Anchor [MATERIAL GAP]

**Decision_kind:** design
**Decision_maker_claimed:** board

## Cross-decision consistency

D1 (SCIP FQN) and D3 (PURL `:ExternalDependency`) are coupled. SCIP symbol's `<package>` field maps directly to `:ExternalDependency`'s `(ecosystem, canonical_name, resolved_version)` triple. SCIP `manager` ∈ {`maven`, `pip`, `cargo`, `npm`} maps 1:1 to `ecosystem`. Per Opus Finding 4, this mapping table must be made explicit in the implementation spec (not just narrated). Action: implementation spec includes a normative SCIP↔ExternalDependency mapping section.

D2 (Hybrid Tantivy+Neo4j) and D4-D8 (memory-bounded layer) are coupled. Tantivy's `heap_size_in_bytes` budget enforces the Tantivy half; Cypher eviction policies enforce the Neo4j half. Both halves must respect `PALACE_MAX_OCCURRENCES_TOTAL` proportionally.

D9 (Serena complementarity) reduces volume, easing D5 budget pressure. Implementation spec must explicitly state which languages skip occurrence indexing in Phase 2/3 (currently: Python, JS, TS, Kotlin, Swift, Rust use sampling; Solidity, FunC, Anchor get full).

## Replication to palace.memory.decide

Each decision above is to be written as a `:Decision` `EntityNode` via `palace.memory.decide` on the iMac docker stack during implementation slice's Phase 1.1. Expected payload shape per decision:

```python
palace.memory.decide(
    title="<D-N name>",
    body="<full body text from this document>",
    decision_kind="design",
    decision_maker_claimed="board",
    confidence=<0.0-1.0>,
    evidence_ref=["<voltagent-research-paths>", "<researchagent-commit>"],
    tags=["pre-extractor-foundation", "GIM-100-followup", "schema-decision"],
    project="gimle",
    slice_ref="GIM-100-ratification",
)
```

This document is the **canonical text source**; the `:Decision` nodes are the **machine-actionable replication** for query via `palace.memory.lookup`.

## Next slice

Implementation begins with `feature/extractor-symbol-index-foundation` slice — see `docs/superpowers/specs/2026-04-27-extractor-symbol-index-foundation-design.md` (this commit).

Foundation slice scope per Option B chosen by Board:
1. Tantivy sidecar setup + integration
2. Schemas (`:SymbolOccurrence`, `:ExternalDependency`, `:EvictionRecord`)
3. Importance score formula + Count-Min Sketch utility
4. 3-round eviction Cypher
5. Tier-aware configuration surface
6. **Plus** first language extractor: Python via scip-python (dogfood test on Gimle-Palace itself)

Subsequent language extractors (Slice 102+) follow the same pattern with ~2-3 day cadence per language: scip-typescript / scip-kotlin / swift-symbolkit / palace-scheme generators for Solidity, FunC, Anchor.
