# Extractors Storage Contract

Palace-mcp uses two distinct storage backends for symbol data. This
document defines which extractor writes where and what each store is
used for.

## Stores

### Tantivy (full-text occurrence index)

- **Granularity**: one document per file:line occurrence (DEF, DECL, USE).
- **Location**: `PALACE_TANTIVY_INDEX_PATH` (docker volume `palace-tantivy-data`
  at `/var/lib/palace/tantivy`).
- **Schema fields**: `doc_key`, `symbol_id`, `repo_id`, `file_path`, `line`,
  `col_start`, `col_end`, `role`, `language`, `commit_sha`, `importance`,
  `ingest_run_id`, `phase`.
- **Primary key**: `doc_key` (delete-then-add for idempotency).
- **Consumers**: `palace.code.find_references`, `semantic_search` usage preview.

### Neo4j `:Symbol` nodes (symbol-level graph)

- **Granularity**: one node per unique `qualified_name` within a `group_id`.
- **Key**: `(qualified_name, group_id)` — unique constraint.
- **Properties**: `kind`, `file_path`, `module_name`, `source_scope`,
  `extends_protocol`, `access_modifier`, boolean attribute flags (`is_objc`,
  `is_dynamic`, etc.), `embedding`, `embedding_input_hash`, `deleted_at`.
- **Relationships written by `symbol_index_*`**: `REFERENCES`, `CONFORMS_TO`,
  `EXTENDS`, `EXTENSION_OF`.
- **Relationships read by `dead_code`**: `CALLS`, `REFERENCES`, `EXTENDS`,
  `CONFORMS_TO`, `EXTENSION_OF`, `EXISTENTIAL_USE` (the graph loader query
  includes `CALLS` and `EXISTENTIAL_USE` for forward-compatibility; they are
  not currently produced by the SCIP-based extractors).
- **Consumers**: `dead_code` (graph reachability), `embedding_symbol` (vector
  population), `semantic_search` (vector query), `dead_symbol_binary_surface`.

## Per-extractor write targets

| Extractor | Tantivy | Neo4j `:Symbol` | Neo4j other | `nodes_written` reports |
|---|---|---|---|---|
| `symbol_index_swift` | occurrences (3-phase) | `:Symbol` + edges | `:IngestRun`, checkpoints | Neo4j `:Symbol` count |
| `symbol_index_python` | occurrences (3-phase) | `:Symbol` + edges | `:IngestRun`, checkpoints | Neo4j `:Symbol` count |
| `symbol_index_typescript` | occurrences (3-phase) | `:Symbol` + edges | `:IngestRun`, checkpoints | Neo4j `:Symbol` count |
| `symbol_index_java` | occurrences (3-phase) | `:Symbol` + edges | `:IngestRun`, checkpoints | Neo4j `:Symbol` count |
| `symbol_index_solidity` | occurrences (3-phase) | `:Symbol` + edges | `:IngestRun`, checkpoints | Neo4j `:Symbol` count |
| `symbol_index_clang` | occurrences (3-phase) | `:Symbol` + edges | `:IngestRun`, checkpoints | Neo4j `:Symbol` count |
| `dead_code` | — | MERGE (upsert) `:Symbol` via `DEAD_SYMBOL` edge; reads `:Symbol` graph | `:DeadFinding`, `:IngestRun` | `:DeadFinding` node count |
| `embedding_symbol` | — | writes `.embedding` on `:Symbol` | — | symbols embedded count |
| `dead_symbol_binary_surface` | — | reads `:Symbol` | extractor-specific nodes | extractor node count |
| `dependency_surface` | — | — | `:ExternalDependency`, `:DEPENDS_ON` | dep node count |
| `git_history` | — | — | `:Commit`, `:Author`, `:File`, `:TOUCHED` | commit+author count |
| `hotspot` | — | — | `:Function`, `:File` properties | function node count |
| `code_ownership` | — | — | `:OWNED_BY` edges | file count |
| `heartbeat` | — | — | `:ExtractorHeartbeat` | 1 |

## Why the counts differ

A single symbol (e.g. `CryptoKit.AES256.encrypt`) may appear in dozens
of files as DEF, DECL, or USE occurrences. Each occurrence is a separate
Tantivy document; the symbol itself is one Neo4j `:Symbol` node. For a
typical Swift kit:

- Tantivy occurrences: 10k–15k (all file:line references)
- Neo4j `:Symbol` nodes: 1.5k–2.5k (unique symbols)

This 5–7x ratio is expected and varies by codebase structure.

## Semantic search data flow

1. **Ingest**: `symbol_index_*` writes occurrences to Tantivy AND `:Symbol`
   nodes to Neo4j.
2. **Embed**: `embedding_symbol` reads `:Symbol` from Neo4j, calls embedding
   backend, writes `embedding` vector back to `:Symbol`.
3. **Query**: `semantic_search` embeds the query text, runs
   `db.index.vector.queryNodes` against `:Symbol.embedding` in Neo4j.
4. **Enrich**: for each result, optionally reads Tantivy via
   `TantivyBridge.search_occurrences_async` for usage preview (file:line
   locations where the symbol appears).

## Historical note

Before GIM-1074 (commit `5537d27`, 2026-05-30), `symbol_index_swift`
reported the Tantivy occurrence count as `nodes_written`. This caused
apparent divergence between the tool response and Neo4j `:Symbol` count.
The fix changed the return to report Neo4j `:Symbol` count, with the
Tantivy count logged separately for observability.
