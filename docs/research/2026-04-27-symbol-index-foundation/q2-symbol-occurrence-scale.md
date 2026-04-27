# Q2 — :SymbolOccurrence storage scale & strategy (voltagent independent track)

Date: 2026-04-27
Track: Board cross-check (parallel to ResearchAgent autonomous track on GIM-100)
Sources count: 33

## Executive recommendation

**Option C (Hybrid):** Graphiti/Neo4j retains symbol-level semantics; Tantivy sidecar stores occurrence corpus. Boundary at `:Symbol` node — semantic above, positional below.

## Why Option A (all-Neo4j) fails

- 50M occurrences × 128 B Block format = 6.4 GB nodes alone
- With 6 props + 1 edge each: 25-40 GB
- Page cache need: 36-40 GB
- **Critical: supernode problem** — popular symbol with 100K+ `:OCCURRENCE_OF` in-edges → O(degree) traversal regardless of indexes. Sub-ms → seconds. **Structural, not tunable.**

## Why not Option B (Tantivy only)

Loses cross-repo call graph traversal (primary value of Graphiti/Neo4j here).

## Why Option D (JIT) loses

Reference query = re-parse all files in repo per request. Seconds latency, CPU-bound. Not horizontally scalable.

## Hybrid boundary

```
Neo4j (Graphiti)              Tantivy sidecar
─────────────────────          ──────────────────────────
:Symbol nodes                  SymbolOccurrence documents
:CALLS / :REFERENCES edges     Fields: symbol_id (fast), repo,
:DEFINED_IN → :File                    file_path, line, col,
:IMPLEMENTS, :EXTENDS                  role (def/ref/impl),
:Module, :Package, :Repo               language, commit_sha
Cross-repo edges               
Qualified-name index           Indexed by symbol_id (fast),
                               file_path (text), line (range)
```

## Tantivy schema (recommended)

```
symbol_id:     FAST + INDEXED (u64 or text hash)
repo_id:       FAST + INDEXED (u64)
file_path:     TEXT + STORED (trigram-friendly)
line:          FAST + INDEXED (u32, range-queryable)
col_start:     FAST (u16)
col_end:       FAST (u16)
role:          FAST + INDEXED (u8: def=1, ref=2, impl=4)
language:      FAST + INDEXED (u8 enum)
commit_sha:    STORED (for staleness detection)
```

Per-doc: ~80-120 B compressed. 50M docs = 4-6 GB on disk, 2-4 GB RAM hot working set.

## Query routing

| Query | Path | Latency |
|---|---|---|
| Go to definition | Neo4j qn lookup → DEFINED_IN edge | <1 ms |
| Find all references | Neo4j → symbol_id → Tantivy term query | 1-10 ms (50M scale) |
| Cross-repo call graph | Neo4j CALLS traversal | <10 ms (depth-2) |
| All symbols in file | Tantivy file_path term query | 2-5 ms |
| Impact analysis (rename) | Both stores merged in bridge | combined |

## Why Tantivy over Lucene/ES

- No JVM (no GC pause risk, predictable Rust allocation)
- Library not service (embed via tantivy-py FFI)
- Append-only segment model fits occurrence ingestion
- Zoekt precedent: Sourcegraph runs 2.6B lines / 166 GB on inverted-index primitive at scale

## Why not PostgreSQL Rockskip

3× .git size storage + 4 hours per GB initial indexing. Tantivy bulk indexer faster + smaller on-disk.

## 5 open gaps for prototyping

1. **Tantivy throughput at occurrence granularity** — published 45K docs/s is structured-document workload; need synthetic 10M occurrence benchmark on iMac
2. **tantivy-py FFI viability** — confirm fast-field range queries + concurrent-read/single-writer model
3. **Symbol-id stability across re-indexing** — SCIP claims stable but extractor version bumps may change
4. **Bridge query P99 under concurrent load** — Neo4j+Tantivy fan-out adds sequential hop; load test fixture needed
5. **Multi-language occurrence volume validation** — 5-10M per mobile-Kit estimate is SPECULATIVE; run scip-kotlin/scip-java against EthWallet locally and count

## Confidence summary

- Storage cost analysis: [HIGH] — multi-source confirmed Neo4j Block format ~128 B/node
- Supernode structural ceiling: [HIGH] — Neo4j community + maintainer blogs converge
- Tantivy throughput claims: [MEDIUM] — single Tantivy 0.22 benchmark, occurrence-specific volume unproven
- Zoekt scale claims: [HIGH] — official Sourcegraph blog at 19K repos / 166 GB
- 5-10M occurrences/repo estimate: [SPECULATIVE] — extrapolated from open-source Go projects, not validated against Kotlin/Swift mobile-Kit

## Top sources

1. neo4j.com/developer/kb/understanding-data-on-disk/ — Block format storage
2. medium.com/neo4j/try-neo4js-next-gen-graph-native-store-format — Block format details
3. jboylantoomey.com/post/neo4j-super-node-performance-issues — Supernode analysis (2024)
4. sourcegraph.com/blog/zoekt-memory-optimizations-for-sourcegraph-cloud (2021) — Zoekt scale
5. github.com/quickwit-oss/tantivy — Tantivy primary
6. quickwit.io/blog/tantivy-0.22 (Apr 2024) — Tantivy benchmarks
7. github.com/sourcegraph/scip/blob/main/scip.proto — SCIP encoding rationale
8. sourcegraph.com/docs/code-navigation/rockskip — PostgreSQL+trigram alternative analyzed
