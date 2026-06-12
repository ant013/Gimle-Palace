# Extractor And Semantic Validity Repair

Grounded in `origin/develop` at `818ae53ed83b6edee3d68774680a2aecb761501a`
and native MacBook palace-mcp smoke evidence collected on 2026-06-12.

## Goal

Make the native Palace extractor and semantic toolchain valid for real operator
questions across the seven expected iOS repos:

- `bitcoin-core`
- `bitcoin-kit`
- `component-kit`
- `dash-kit`
- `evm-kit`
- `hd-wallet-kit`
- `uw-ios-app`

Valid means the graph has real project-source symbols, semantic embeddings are
populated enough to answer scoped questions, call/reference-dependent tools do
not silently return misleading answers, and MCP code tools accept or translate
the identifiers emitted by sibling tools.

## Evidence From Native Audit

Native service:

- `work.ant013.palace-mcp-native`, `http://127.0.0.1:8765`
- `healthz`: `{"status":"ok","neo4j":"reachable"}`
- `palace.memory.health`: `File=73979`, `Symbol=872786`,
  `code_graph_reachable=true`
- Runtime issue fixed during audit: launchd plist had
  `PALACE_MEMORY_EMBEDDER=noop`; removing that override enabled Qodo/MPS
  embedding.

Static/test gates in `/Users/Shared/Ios/Gimle-Palace/services/palace-mcp`:

- `uv run ruff check` passed.
- `uv run ruff format --check` passed.
- `uv run mypy src/` passed.
- `uv run pytest` collected 3101 items: `2818 passed`, `278 skipped`,
  `5 errors`. The 5 errors are Docker/testcontainers integration setup errors
  in `tests/integration/test_project_analyze_start_run_integration.py`; these
  must not be pointed at production native Neo4j because the fixture deletes
  all nodes.

Current graph evidence after audit:

| Project | Files | Symbols | Embedded | Project symbols | Project embedded | Occurrence shadows | Semantic edges |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `bitcoin-core` | 3,766 | 48,166 | 1,088 | 7,154 | 1,088 | 8,853 | 0 |
| `bitcoin-kit` | 3,736 | 48,490 | 0 | 219 | 0 | 8,935 | 0 |
| `component-kit` | 994 | 11,836 | 11,836 | 0 | 0 | 3,177 | 0 |
| `dash-kit` | 3,818 | 49,788 | 0 | 1,596 | 0 | 9,220 | 0 |
| `evm-kit` | 2,166 | 44,661 | 44,661 | 3,181 | 3,181 | 8,066 | 0 |
| `hd-wallet-kit` | 63 | 226 | 226 | 0 | 0 | 39 | 0 |
| `uw-ios-app` | 28,410 | 254,764 | 0 | 69,987 | 0 | 56,733 | 0 |

Observed failures:

1. `dead_code` is not semantically valid for the seven repos. Running it on
   missing projects returned `outcome=missing_input`: many `:Symbol` nodes but
   zero `REFERENCES/CALLS/EXTENDS/CONFORMS_TO/EXTENSION_OF/EXISTENTIAL_USE`
   edges.
2. The real `.scip/index.scip` files checked for `hd-wallet-kit`,
   `component-kit`, and `evm-kit` have `relationship_count=0`, so the current
   symbol writer cannot materialize reachability edges from them.
3. `component-kit` and `hd-wallet-kit` current SCIP data is dependency-only:
   sample paths are `Example/Pods/...`; project source symbols are missing.
4. `palace.code.semantic_search` works for `evm-kit` after embeddings:
   query `ethereum address transaction signature nonce gas` returns
   `Sources/EvmKit/Models/Transaction.swift`. It is not generally valid:
   dependency-only/small projects can return zero because vector search queries
   the global index with too-small `query_k` before project/scope filtering.
5. `palace.code.find_references` returned false-positive occurrences for an
   exact Swift SCIP qname: requested `EvmKit.Transaction.nonce`, returned
   `CryptoKit.AES...Nonce` occurrences.
6. `palace.code.get_snippet_rich` rejects Swift SCIP qnames emitted by
   `semantic_search`; it validates only dotted Python-style identifiers.
7. `palace.code.search_graph` does not expose the native `:Symbol` surface:
   `label="Symbol"` is rejected, and searching `Transaction` in `evm-kit`
   returns zero despite matching `:Symbol` nodes.
8. Long `embedding_symbol` MCP calls block interactive MCP latency in the
   single native server process. `evm-kit` took about 67 minutes for 44,661
   vectors.

Tools observed as returning real data:

- `palace.code.semantic_search` for `evm-kit`
- `palace.code.list_functions`
- `palace.code.find_hotspots`
- `palace.code.find_public_api`
- `palace.code.find_dead_symbols`

Historical regression note:

- `dead_code` did work before the native/refactor path regressed. `docs/roadmap.md`
  records G0d as closed on 2026-05-23 with `UW dead_code = 5926 findings,
  5926 edges`.
- Commit `c095a539399b2c774226ab7084f9cafc6bccddb6` on 2026-06-08 added the
  current zero-edge preflight guard after native ingest produced `250 595`
  isolated `:Symbol` nodes and hit the 3600 s timeout. That commit changed the
  failure mode from "hang / classify everything dead" to `missing_input`; it
  did not restore the relationship substrate.
- Therefore the repair is not to remove the guard blindly. The repair is to
  restore the relationship-producing substrate for native ingest and keep the
  guard as a safety net for genuinely edge-empty input.

## Assumptions

- Native MacBook + local Neo4j is the authoritative smoke environment for this
  validation work. Docker is only acceptable for isolated destructive test DBs,
  not for normal MacBook semantic smoke.
- The expected profile is the seven iOS repos listed above.
- iMac deployment happens after merge; it is not the place to run MacBook MPS
  embedding validation.
- Existing secrets stay in `.env` and must not be committed or pasted into
  docs, logs, PR comments, or issues.

## Scope

In scope:

- Repair semantic search candidate retrieval and scope filtering so scoped
  project queries are reliable even when global vector results are dominated by
  other projects or dependencies.
- Repair identifier compatibility between `semantic_search`, `find_references`,
  `get_snippet_rich`, and `search_graph`.
- Repair or document the SCIP generation path so expected repos produce project
  source symbols and relationship metadata when possible.
- Add guardrails so call-graph-dependent tools expose `missing_input` rather
  than misleading empty or false-positive answers.
- Add native validation scripts or tests that can run safely without deleting
  production Neo4j.

Out of scope:

- Running destructive testcontainers tests against production native Neo4j.
- iMac deployment changes before a PR merges to `develop`.
- Broad UI/frontend work.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/code/native_search_graph.py`
- `services/palace-mcp/src/palace_mcp/code_composite.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`
- Native smoke scripts/runbooks under `services/palace-mcp/scripts/` and
  `docs/runbooks/`
- Tests under `services/palace-mcp/tests/`

## Acceptance Criteria

- `palace.code.semantic_search(project="evm-kit", query="ethereum address transaction signature nonce gas")`
  returns at least 5 scoped, project-source results with file paths.
- `palace.code.semantic_search(project="hd-wallet-kit", query="base58 encode decode wallet address", include_dependencies=true)`
  returns scoped results instead of `scope_filter_underfilled`.
- `palace.code.search_graph(project="evm-kit", name_pattern="Transaction")`
  can find native `:Symbol` data or returns a documented unsupported contract
  that does not contradict `semantic_search`.
- `palace.code.get_snippet_rich` accepts an identifier emitted by
  `semantic_search`, or `semantic_search` emits a compatible identifier field.
- `palace.code.find_references` never returns occurrences for a different
  qualified name than requested without an explicit ambiguity envelope.
- `dead_code` remains `missing_input` until relationship edges exist, and the
  message points at the actual missing substrate rather than an incorrect
  Docker or stale bridge assumption.
- At least one repo has nonzero
  `REFERENCES/CALLS/EXTENDS/CONFORMS_TO/EXTENSION_OF/EXISTENTIAL_USE` edges
  after the repaired ingest path, or the spec documents why the current SCIP
  generator cannot produce them and gates dead-code features accordingly.
- Component/HD wallet kit SCIP generation includes project source symbols, or
  those repos are explicitly marked unsupported for first-party semantic search.

## Verification Plan

Local static gates:

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
```

Targeted tests:

```bash
cd services/palace-mcp
uv run pytest tests/code* tests/code_composite* tests/extractors/unit -q
```

Native MCP smoke:

- `palace.memory.health`
- `palace.ingest.run_extractor(name="symbol_index_swift", project="evm-kit")`
- `palace.ingest.run_extractor(name="embedding_symbol", project="evm-kit")`
- semantic/search/reference/snippet matrix from this spec's acceptance criteria

Data invariants:

```cypher
MATCH (p:Project)
WHERE p.slug IN ["bitcoin-core","bitcoin-kit","component-kit","dash-kit","evm-kit","hd-wallet-kit","uw-ios-app"]
MATCH (s:Symbol {group_id:p.group_id})
RETURN p.slug, count(s), count(s.embedding),
       sum(CASE WHEN s.source_scope = "project" THEN 1 ELSE 0 END)
```

```cypher
MATCH (p:Project {slug:"evm-kit"})
MATCH (:Symbol {group_id:p.group_id})-[r:REFERENCES|CALLS|EXTENDS|CONFORMS_TO|EXTENSION_OF|EXISTENTIAL_USE]->(:Symbol {group_id:p.group_id})
RETURN count(r)
```

## Open Questions

- Which SCIP generator command is authoritative for Swift, and can it emit
  `SymbolInformation.relationships` for the needed call/reference graph?
- Should native `search_graph` be extended to query Palace `:Symbol` nodes, or
  should it stay a narrower CM-compatible facade with a clearer contract?
- Should `semantic_search` query vector candidates per project/scope instead of
  querying the global index then filtering?
- Should long extractors run out-of-process/job-style so interactive MCP tools
  stay responsive during embedding?
