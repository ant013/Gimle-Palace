# Gimle Capability Smoke Follow-Ups

Grounded in `origin/develop` at
`818ae53ed83b6edee3d68774680a2aecb761501a` and branch
`fix/extractor-semantic-validity-audit` at `f1a30947`.

Native audit artifacts:

- `/tmp/gimle-deep-capability-smoke-20260613-103902.json`
- `/tmp/gimle-deep-capability-smoke-20260613-103902.md`
- `/tmp/gimle-supplemental-capability-smoke-20260613-104755.json`
- `/tmp/gimle-supplemental-capability-smoke-20260613-104755.md`
- `/tmp/gimle-call-hierarchy-smoke-20260613-104755.json`

## Goal

Turn the deep Gimle capability smoke from an ad-hoc `/tmp` audit into a
repeatable native validation suite and fix the tool defects it exposed.

This is not a Docker task. Native MacBook Neo4j, native palace-mcp, Xcode
DerivedData/IndexStore, and native `.env` are the authoritative smoke substrate.

## Evidence

Main smoke:

- `137` cases total.
- `130` OK.
- `7` failed.
- `61` OK but empty.
- `palace.code.semantic_search`: `50/50` OK, `30` empty.
- `palace.code.semantic_search.cross`: `15/15` OK, every case returned `8`
  results.
- `palace.code.find_hotspots`: `10/10` OK.
- `palace.code.list_functions`: `12/12` OK.
- `palace.code.find_owners`: `12/12` OK, `5` empty.
- `palace.code.find_version_skew.bundle`: OK, `23` skew groups
  (`1 major`, `5 minor`, `1 patch`, `16 unknown`).

Supplemental smoke:

- `32/32` OK for `find_dead_code`, `find_dead_symbols`,
  `find_public_api`, and project-level `find_version_skew`.

Call hierarchy smoke:

- `5/5` OK with explicit DataStore path.
- Real callers found for `SwapView`, `SendView`, and `AppDelegate`.
- Native `.env` currently has `PALACE_INDEXSTORE_PATHS={}`, so the tool is not
  discoverable by project without an explicit path.

Graph counts from direct native Neo4j inspection:

| Surface | Nonzero projects / counts |
| --- | --- |
| `DeadFinding` | all 16 indexed projects; `uw-ios-app=254758`, `stable-wallet-ios=1508` |
| `DeadSymbolCandidate` | 8 projects; `stable-wallet-ios=2286`, `uw-ios-app=1137` |
| `PublicApiSymbol` | 4 projects; `bitcoin-core=695`, `evm-kit=386`, `dash-kit=26`, `bitcoin-kit=7` |
| `ExternalDependency` | 10 projects; `uw-ios-baseline=97`, `bitcoin-core=9`, others smaller |

## Problems To Solve

### P0: `palace.memory.list_projects` crashes on Neo4j temporal values

Observed failure:

```text
ValidationError: source_updated_at Input should be a valid string
input_value=neo4j.time.DateTime(...)
```

Current analog:

- `palace_mcp.memory.lookup._serialize_props` already converts values with
  `iso_format()`.
- `palace_mcp.memory.project_tools._project_info_from_row` passes Project node
  properties directly into `ProjectInfo`.

Fix direction:

- Add a small local timestamp normalizer in `memory/project_tools.py`, or reuse
  the lookup serializer if doing so does not create an awkward dependency.
- Normalize `source_created_at`, `source_updated_at`, and last-ingest timestamps.
- Add unit regression for Neo4j-like objects exposing `iso_format()`.

### P0: `palace.memory.lookup(project=<slug>)` rejects real project slugs

Observed failures:

- `palace.memory.lookup(project="uw-ios-app")` → `unknown_project`.
- `palace.memory.lookup(project="dash-kit")` → `unknown_project`.
- `palace.memory.lookup(project="bitcoin-kit")` → `unknown_project`.

Root cause candidate:

```python
LIST_PROJECT_SLUGS = "MATCH (p:Project) RETURN p.name AS slug ORDER BY slug"
```

`resolve_group_ids()` treats this result as canonical slugs. For many projects
`p.name` is a human repo name such as `unstoppable-wallet-ios` or
`DashKit.Swift`, while the MCP API requires `p.slug` such as `uw-ios-app` and
`dash-kit`.

Fix direction:

- Change `LIST_PROJECT_SLUGS` to return `p.slug AS slug`.
- Add tests where `name != slug` and `lookup(project=<slug>)` resolves.
- Verify `project="*"` still returns `project/<slug>` group ids.

### P1: `palace.memory.get_project_overview` reports empty code counts

Observed:

- Overview succeeds for code projects but `entity_counts={}` and ingest
  timestamps are null.
- Direct graph counts show `Symbol`, `File`, `Function`, `DeadFinding`,
  `DeadSymbolCandidate`, `PublicApiSymbol`, and `ExternalDependency` are present.

Root cause candidates:

- `PROJECT_ENTITY_COUNTS` only includes the older Graphiti label set and omits
  current extractor labels such as `DeadFinding`, `DeadSymbolCandidate`,
  `PublicApiSymbol`, `ExternalDependency`, and several diagnostic labels.
- `get_project_overview()` filters returned labels down to
  `Issue`, `Comment`, `Agent`, and `IngestRun`.
- Last-ingest query defaults to `source="paperclip"`, which is not the primary
  code extractor source.

Fix direction:

- Expand entity counts to include current code/extractor labels.
- Return counts with stable keys that are useful for operator smoke:
  `Symbol`, `EmbeddedSymbol`, `File`, `Function`, `Commit`, `DeadFinding`,
  `DeadSymbolCandidate`, `PublicApiSymbol`, `ExternalDependency`, and
  `IngestRun`.
- Either make last-ingest source optional for code projects or add a code-source
  overview path that reports the newest `IngestRun` for the project.

### P1: schema drift warnings in code tools

Observed warnings:

- `palace.code.semantic_search` returns `s.line_start` / `s.line_end`, but many
  current `:Symbol` nodes do not have those properties.
- `palace.code.find_dead_code` returns `git_last_external_ref` and
  `target_dead_type`, but current `:DeadFinding` nodes do not have those
  properties.

Fix direction:

- Treat missing optional properties as null without noisy Neo4j warnings, using
  `coalesce` or versioned field projection where appropriate.
- Add tests around current writer schema.

### P1: call hierarchy works only with explicit path

Observed:

- Direct call with
  `/Users/ant013/Library/Developer/Xcode/DerivedData/Wallet-gymhapnhfvxttoggofbrsswxcwig/Index.noindex/DataStore`
  works.
- Native `.env` has `PALACE_INDEXSTORE_PATHS={}`.

Fix direction:

- Decide whether this is code or environment:
  - environment-only: populate native `.env` with `stable-wallet-ios` and any
    other known DataStore paths;
  - code: add best-effort project DataStore discovery only if it can be safe and
    deterministic.
- At minimum, improve tool error message to include the expected env key and
  project-specific mapping example.

### P2: `30` empty single-repo semantic answers

Observed:

- Empty responses were mostly caused by applying app-oriented generic text to
  low-level kit/toolkit repos:
  - `swap token selection balance deposit wallet connect`
  - `seed phrase restore backup passcode app lock`
  - `evm transaction gas fee nonce signer`
- Cross-repo semantic was healthy: `15/15` returned results.
- Repo-specific queries did work where the query matched the repo domain:
  `market-kit` returned market hits, `evm-kit` returned EVM hits, etc.

Interpretation:

- This is not primarily an embedding infrastructure failure. It is a smoke-test
  design gap: one generic app query pack is not a fair validity test for every
  low-level repo.
- The tool should still help the operator understand empty results. Empty
  should include enough diagnostics to distinguish "query mismatched this repo"
  from "embeddings missing" or "scope filtered everything out".

Fix direction:

- Add a checked-in native capability smoke runner with repo archetype query
  packs:
  - app wallet queries for `uw-ios-app`, `stable-wallet-ios`;
  - EVM queries for `evm-kit`;
  - UTXO/Bitcoin queries for `bitcoin-core`, `bitcoin-kit`, `litecoin-kit`,
    `dash-kit`;
  - market data queries for `market-kit`;
  - UI/component queries for `component-kit`;
  - crypto/mnemonic queries for `hs-crypto`, `hd-wallet-kit`;
  - utility/logging/networking queries for `hs-toolkit`, `hs-extensions`.
- Keep a separate intentionally generic query pack, but score it as
  broad-discovery coverage rather than per-repo failure.
- Enhance semantic empty diagnostics to include:
  - embedded symbol count;
  - candidate count before source-scope filtering;
  - `scope_excluded_count`;
  - top excluded source scopes when available;
  - guidance to retry with `include_dependencies` or a repo-specific query pack
    when appropriate.

## Assumptions

- The current task continues on branch `fix/extractor-semantic-validity-audit`;
  it is already based on and ahead of `origin/develop`.
- Changes remain scoped to `services/palace-mcp` plus docs/scripts needed for
  native validation.
- No secrets are committed. Native `.env` edits, if needed, are local
  operational steps and must not be committed.
- Docker is not required for the native smoke path.

## Scope

In scope:

- Fix `palace.memory.list_projects` temporal serialization.
- Fix project slug resolution for `palace.memory.lookup`.
- Make `palace.memory.get_project_overview` useful for code/extractor projects.
- Reduce schema-drift warning noise in semantic/dead-code read tools.
- Add or formalize native capability smoke scripts that preserve the audit
  matrix and repo-specific query packs.
- Verify call hierarchy with explicit native IndexStore path and document or
  improve project-path configuration.

Out of scope:

- Changing the embedding model.
- Claiming every arbitrary natural-language question must return non-empty
  results for every repo. A low-level kit can validly return empty for unrelated
  app UI questions.
- Destructive testcontainers runs against production native Neo4j.
- iMac deployment before PR merge.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/src/palace_mcp/memory/project_tools.py`
- `services/palace-mcp/src/palace_mcp/memory/projects.py`
- `services/palace-mcp/src/palace_mcp/memory/lookup.py`
- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/code/find_dead_code.py`
- `services/palace-mcp/src/palace_mcp/code/call_hierarchy_v2.py`
- `services/palace-mcp/tests/memory/test_project_tools.py`
- `services/palace-mcp/tests/memory/`
- `services/palace-mcp/tests/code/`
- native smoke script location to be selected under `services/palace-mcp/scripts/`
  or `tools/`

## Acceptance Criteria

- `palace.memory.list_projects()` succeeds against native Neo4j and returns
  all 16 registered projects.
- `palace.memory.lookup(entity_type="Symbol", project="uw-ios-app", ...)` no
  longer returns `unknown_project` for registered slugs. Empty result is allowed
  only when no matching entity exists.
- `palace.memory.get_project_overview("uw-ios-app")` reports nonzero code counts
  including at least `Symbol` and `File`.
- `palace.code.find_dead_code(project="stable-wallet-ios", limit=10)` returns
  findings without noisy missing-property warnings.
- `palace.code.semantic_search` empty responses include actionable diagnostics
  rather than only `returned_count=0`.
- A checked-in native capability smoke can run the core matrix without manual
  one-off `/tmp` scripts and can write JSON/Markdown reports outside the repo.
- Repo-aware semantic smoke shows nonzero results for each indexed repo using
  a query pack appropriate to that repo's domain, or records a concrete
  `project_not_indexed` / `embeddings_not_ready` / `unsupported_surface` reason.
- Cross-repo semantic smoke remains green: at least 3 multi-project scopes and
  5 query texts each return nonzero results.
- Call hierarchy smoke is documented with explicit IndexStore path handling; if
  project-path config is added, `project="stable-wallet-ios"` works without
  passing `index_store_path`.

## Verification Plan

Targeted unit tests:

```bash
cd services/palace-mcp
uv run pytest tests/memory/test_project_tools.py tests/code/test_find_semantic.py -q
```

Static checks:

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
```

Native smoke:

```bash
cd services/palace-mcp
uv run python <native-capability-smoke-script> --env /Users/ant013/Android/Gimle-Palace-native/.env --out /tmp
```

Direct native invariants:

```cypher
MATCH (p:Project)
RETURN p.slug, p.name, p.group_id
ORDER BY p.slug
```

```cypher
MATCH (s:Symbol {group_id:"project/uw-ios-app"})
RETURN count(s) AS symbols, count(s.embedding) AS embedded
```

```cypher
MATCH (d:DeadFinding {project:"stable-wallet-ios"})
RETURN count(d) AS dead_findings
```

## Open Questions

- Should `get_project_overview` remain a memory/Graphiti-oriented endpoint and
  add code counts opportunistically, or should we introduce a separate
  `palace.code.project_overview` later? Recommendation: improve current
  endpoint now because operators already use it for tool readiness.
- Should `PALACE_INDEXSTORE_PATHS` be updated locally as part of this task, or
  should project DataStore discovery be coded? Recommendation: local env update
  now, code discovery only if the path can be selected deterministically.
- Should generic app-oriented semantic queries be considered a failure for
  low-level kits? Recommendation: no. Treat them as broad-discovery checks and
  require repo-domain query packs for validity.

## Analog Notes

- Timestamp normalization analog:
  `palace_mcp.memory.lookup._serialize_props` converts values with
  `iso_format()`.
- Project tools test analog:
  `tests/memory/test_project_tools.py` already covers null timestamps and
  sorted list results.
- Semantic scope diagnostics analog:
  `tests/code/test_semantic_filtering.py` already asserts
  `scope_excluded_count` and include flags.
- Version skew and dead/public supplemental smoke show the current read-tool
  envelope shape is acceptable when project selection is correct.

