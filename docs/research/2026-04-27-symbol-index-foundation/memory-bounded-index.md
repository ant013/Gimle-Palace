# Memory-Bounded Persistent Code Index — Research Findings (compact)

Date: 2026-04-27
Track: Board independent research для bounded-memory adaptive strategy
Sources: 36 (Sourcegraph, GitHub, Mozilla, Meta, Google, Neo4j, RocksDB, Tantivy, Lucene, Cursor)

## Главное открытие

**Все production code-intelligence системы решают одну и ту же проблему по-разному:**

| Система | Стратегия |
|---|---|
| Sourcegraph/Zoekt | PageRank на undirected reference graph; mmap + OS page cache eviction |
| GitHub Blackbird | Lazy iterators, никогда не загружает полный index в RAM |
| Mozilla Searchfox | Static HTML генерация, kind-faceted priority (def > decl > use) |
| Meta Glean | Immutable database stacking — drop entire layer для cold tier eviction |
| Tantivy | Single `heap_size_in_bytes`, автоматический flush при достижении |
| Lucene | MMap-only, OS page cache решает что хранить |

**Никто не реализует "importance threshold для решения что persist"** — это open opportunity для palace-mcp.

## Рекомендованная формула importance (compute at ingest time)

```
importance = clamp(
    0.35 * log1p(cms_in_degree) / log1p(100)  # centrality (CMS approximated)
  + 0.30 * tier_weight                          # 1.0 user / 0.5 first-party / 0.1 vendor
  + 0.20 * kind_weight                          # def=1.0, decl=0.8, assign=0.5, use=0.3
  + 0.10 * exp(-days_since_last_seen / 30.0)   # recency half-life 30d
  + 0.05 * language_weight                      # primary lang=1.0, others=0.7
, 0.0, 1.0)
```

`cms_in_degree`: Count-Min Sketch (~2 MB RAM на 70M symbols), O(1) per write. Корреляция с PageRank высокая для sparse symbol graphs.

## 3-tier importance стратегия (для extractor #21)

**Tier 1 — ALWAYS KEEP** (5-10% объёма, 100% структурной ценности):
- Symbol definitions (Function/Class/Method)
- Graph edges (CALLS, TESTS, IMPLEMENTS, BRIDGES_TO)
- Decision nodes

**Tier 2 — NEGOTIABLE** (50-60%, drop по importance):
- User-code occurrences (kind='use' в src/, app/)
- Test → tested-symbol references
- Security-relevant pattern matches (`exec`, `eval`, `system`)
- Recently modified code

**Tier 3 — SACRIFICIAL** (30-40%, evict first):
- Stdlib uses (print, forEach, console.log)
- Vendor / node_modules / .pods occurrences
- Comments, docstrings

## Eviction policy (3-round Cypher)

```cypher
-- Round 1: vendor/stdlib uses
MATCH (o:SymbolOccurrence)
WHERE o.importance < 0.2 AND o.kind = 'use' AND o.tier_weight <= 0.1
WITH o ORDER BY o.importance ASC, o.last_seen_at ASC
LIMIT 100000
DETACH DELETE o

-- Round 2: low-importance user uses из inactive projects
MATCH (o:SymbolOccurrence)
WHERE o.importance < 0.4 AND o.kind = 'use'
  AND o.last_seen_at < datetime() - duration({days: 90})
WITH o ORDER BY o.importance ASC LIMIT 100000
DETACH DELETE o

-- Round 3: assign records (последняя инстанция)
MATCH (o:SymbolOccurrence)
WHERE o.importance < 0.3 AND o.kind = 'assign'
WITH o ORDER BY o.importance ASC LIMIT 100000
DETACH DELETE o

-- НИКОГДА не evict kind='def' / 'decl' автоматически
```

## Configuration surface

```yaml
PALACE_MAX_OCCURRENCES_TOTAL=50000000     # default 50M
PALACE_MAX_OCCURRENCES_PER_PROJECT=10000000  # 10M cap per project
PALACE_IMPORTANCE_THRESHOLD_USE=0.15      # below = drop at ingest
PALACE_MAX_OCCURRENCES_PER_SYMBOL=5000    # CMS-enforced cap per symbol
PALACE_RECENCY_DECAY_DAYS=30
```

## Tier-appropriate defaults

| Machine | RAM | MAX_OCCURRENCES_TOTAL | IMPORTANCE_THRESHOLD_USE | Coverage |
|---|---|---|---|---|
| **8 GB VPS** | 8 GB | 5M | 0.35 | Defs + high-importance uses only |
| **16 GB MacBook** | 16 GB | 15M | 0.20 | Defs + most user-code uses |
| **32 GB workstation** | 32 GB | 30M | 0.10 | Near-full user-code coverage |
| **64 GB iMac (current)** | 64 GB | 70M | 0.00 | Full coverage |

## 3-phase bootstrap для fresh installs на small machines

1. **Phase 1 (all tiers):** Index только `kind=def` + `kind=decl` — 5-10% volume, 100% navigation value. Минуты, immediate usefulness для "go to definition".
2. **Phase 2 (conditional):** Если budget < 50% used → ingest user-code `kind=use` с filter по `IMPORTANCE_THRESHOLD_USE`. Главный quality jump.
3. **Phase 3 (64 GB only):** vendor/stdlib uses с importance > threshold. Skip на <32GB.

## Failure modes — graceful degradation

**Silent empty result risk** → mitigation: `:EvictionRecord` nodes track which symbols evicted. Query response добавляет warning:
```json
{
  "ok": true,
  "tests": [...],
  "total_found": 47,
  "warning": "partial_index",
  "eviction_note": "12 occurrences evicted on 2026-04-27; coverage may be incomplete",
  "coverage_pct": 79
}
```

**Budget overshoot circuit breaker:** если live count > 1.1× MAX → abort ingestion с `error_code: budget_exceeded`.

**OOM prevention:** дефолтные значения в таблице выше calibrated так что 70M × 200B = 14 GB store fits в page cache 64 GB host; scale пропорционально.

## Сравнение алгоритмов eviction

Лучшие современные cache replacement policies:
- **SIEVE (NSDI 2024)** — простейший: single FIFO + visited bit. <20 строк изменений в LRU codebase. Reduces ARC miss ratio на 1.5% mean (63.2% max).
- **S3-FIFO (SOSP 2023)** — три FIFO queue, lock-free. Adopted by Google/VMware. Outperforms LRU на 856B production traces.
- **ARC (USENIX FAST 2003)** — adaptive recency/frequency balance. ZFS, IBM. 10-20% лучше LRU.

Для **persistent Neo4j store** — НИ ОДИН из них напрямую не подходит. SIEVE/S3 нужны in-process visited bits на каждой ноде; Neo4j не предоставляет этого. Поэтому используем **stored importance score как замену visited bit** — это структурный эквивалент, выживает restart.

## Open gaps (требуют prototype)

1. **Per-symbol in-degree без full graph scan** — CMS approximation cheap, но collisions без ground truth исправить нельзя. Weekly job через GDS PageRank — accurate, but требует Neo4j GDS plugin.
2. **Cross-project eviction fairness** — per-project caps mitigate, но не eliminate. Round-robin scheduler нужен для гарантии.
3. **Incremental re-importance scoring** — на каждом edit меняются in-degrees референцируемых symbols. Recompute всех — дорого. Delta-based — стандарт но требует change-tracking.
4. **Recency cold start** — на fresh install last_seen_at = ingest_time для всего; recency не различает symbols. Acceptable для bootstrap.
5. **Vector-based importance альтернатива** — Cursor/Kilo Code используют embeddings. Trade-off: ingest compute cost vs query relevance.

## Top sources

1. Sourcegraph "Ranking in a Week" — PageRank undirected, production
2. SOSP 2023 S3-FIFO — modern cache eviction
3. NSDI 2024 SIEVE — simplest production-grade
4. Meta Glean — immutable stacking model
5. RocksDB Tiered Storage — temperature-based
6. Tantivy heap_size_in_bytes — bounded write buffer
7. Neo4j Memory Configuration — page cache tuning
8. Google Cloud "Design for graceful degradation"
