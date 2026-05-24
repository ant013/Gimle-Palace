# GIM-839 MacBook Semantic Smoke Readiness

## Goal

Make `G0.5.6` / `G0.5.7` runnable on a MacBook tomorrow without another
runtime archaeology session:

- bring up `palace-mcp` locally;
- populate a bounded set of `:Symbol.embedding` rows with Qodo embeddings;
- run `palace.code.semantic_search` against those rows;
- collect Neo4j counts and a validation transcript that can close the walker
  slice or identify the remaining product gap.

## Current Evidence

2026-05-24 iMac run found that `origin/develop` is merged but not operationally
ready for the cascade:

- `embedding_symbol` is registered and callable.
- Qodo model snapshot downloads successfully when preloaded with
  `HF_HUB_DISABLE_XET=1`.
- The default dependency range
  `sentence-transformers>=3.0.0` resolved to a drifting stack that broke Qodo
  remote code in multiple ways:
  - `Qwen2Config.rope_theta` removed / moved under `rope_parameters`;
  - `tokenization_qwen2_fast` unavailable in the tested Transformers 5.x path;
  - `DynamicCache` legacy methods missing.
- `palace-mcp` needs more than 8 GiB during the first Qodo encode batch.
  Runtime was raised to 12 GiB for the iMac experiment.
- A hotpatched live container wrote the first embeddings:
  `bitcoin-core symbols=7154, embeddings=128`.
- iMac CPU inference is too slow for an unbounded 5-project cascade. Full
  `uw-ios-app` embedding population must not be the first smoke target.

## Assumptions

- Tomorrow's smoke host is an Apple Silicon MacBook with enough RAM for a
  1.5B embedding model.
- Neo4j remains the production graph store for the smoke; no schema reset is
  required.
- The Qodo model remains the target production embedding backend, but smoke may
  be bounded by symbol count and batch size.
- The existing `palace.code.semantic_search` tool is in scope only for runtime
  validation, not API redesign.
- The five GIM-839 projects remain:
  `bitcoin-core`, `evm-kit`, `bitcoin-kit`, `dash-kit`, `uw-ios-app`.

## Scope

### In Scope

1. Stabilize the Qodo backend for current HuggingFace/Transformers drift.
2. Add operator controls for bounded MacBook smoke:
   - embedding batch size;
   - max symbols per extractor run;
   - local-files-only mode for repeat runs after model preload.
3. Add a MacBook smoke runbook with exact commands and expected counts.
4. Add tests that pin the compatibility layer and smoke controls.
5. Update roadmap status text only after the actual smoke transcript exists.

### Out of Scope

- Closing G0.5.6 without a real MacBook transcript.
- Full `uw-ios-app` 70k+ symbol embedding population as the first smoke.
- Replacing Qodo with a different production embedding model.
- Long-running background scheduler for embeddings.
- Multi-tenant/security hardening; that belongs to G0f.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/embeddings/qodo.py`
- `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py`
- `services/palace-mcp/src/palace_mcp/config.py` if env-backed controls are
  placed in `Settings`
- `services/palace-mcp/pyproject.toml` / lockfile only if a resolver-safe pin is
  chosen
- `services/palace-mcp/tests/embeddings/test_qodo_backend.py`
- `services/palace-mcp/tests/extractors/unit/test_embedding_symbol_extractor.py`
- new or updated runbook under `docs/runbooks/semantic-search.md`
- optional helper script under `paperclips/scripts/` or `services/palace-mcp/scripts/`

## Proposed Implementation

### 1. Qodo Compatibility Layer

Add a small, tested compatibility adapter around Qodo loading. It should handle
the exact drift seen on iMac:

- expose `Qwen2Config.rope_theta` when Transformers stores it in
  `rope_parameters`;
- force slow tokenizer loading or otherwise avoid the missing
  `tokenization_qwen2_fast` path;
- adapt `DynamicCache` legacy methods expected by Qodo remote code:
  `from_legacy_cache`, `get_usable_length`, `to_legacy_cache`.

The implementation should be isolated in `qodo.py`, with comments explaining
that it is a compatibility shim for Qodo remote code vs current Transformers,
not a generic Transformers monkeypatch.

### 2. Bounded Embedding Extractor Controls

Add env-backed controls used by `embedding_symbol`:

- `PALACE_EMBEDDING_BATCH_SIZE`, default `64`;
- `PALACE_EMBEDDING_MAX_SYMBOLS`, default unset / no limit;
- `PALACE_QODO_LOCAL_FILES_ONLY`, default `false`.

The max-symbol limit is only for smoke and should be reflected in
`ExtractorStats` metadata if the existing stats type supports it; otherwise the
runbook must require a follow-up count query.

### 3. MacBook Smoke Runbook

Add `docs/runbooks/semantic-search.md` with:

- model preload command;
- MacBook local bring-up command;
- optional container/runtime memory note;
- bounded extractor command for one small kit first;
- count query;
- semantic search query;
- escalation path when Qodo is too slow or not loaded.

The first smoke should be intentionally small:

1. `bitcoin-core` with `PALACE_EMBEDDING_MAX_SYMBOLS=256`;
2. `semantic_search(query="signature verification", project="bitcoin-core")`;
3. only then move to `evm-kit` / `bitcoin-kit` / `dash-kit`;
4. defer `uw-ios-app` full population until bounded smoke passes.

### 4. Optional Helper Script

If the command sequence is too fragile, add an idempotent helper script:

```bash
services/palace-mcp/scripts/smoke_semantic_search_macbook.sh <project> [max_symbols]
```

It should:

- verify MCP health;
- print dependency versions;
- run `symbol_index_swift`, `dead_code`, `embedding_symbol`;
- print per-project Neo4j counts;
- run one semantic search query;
- exit non-zero if embeddings remain zero.

## Acceptance Criteria

1. Unit tests cover the Qodo compatibility adapter without loading the real
   model.
2. Unit tests cover `PALACE_EMBEDDING_BATCH_SIZE` and
   `PALACE_EMBEDDING_MAX_SYMBOLS`.
3. `uv run pytest` for the touched unit tests passes locally.
4. Runbook has exact MacBook commands and expected output shape.
5. MacBook smoke can produce:
   - `count(s.embedding) >= 128` for `bitcoin-core` or another small kit;
   - `palace.code.semantic_search(...).ok == true`;
   - at least one returned hit with `qualified_name`, `file_path`, `score`, and
     context when `include_context=true`.
6. The final smoke transcript includes:
   - dependency versions;
   - model cache path;
   - project counts before/after;
   - semantic search top 3;
   - elapsed time.

## Verification Plan

Before MacBook smoke:

```bash
cd services/palace-mcp
uv run pytest tests/embeddings/test_qodo_backend.py \
  tests/extractors/unit/test_embedding_symbol_extractor.py
uv run ruff check src/palace_mcp/embeddings/qodo.py \
  src/palace_mcp/extractors/embedding_symbol.py
uv run mypy src/palace_mcp/embeddings/qodo.py \
  src/palace_mcp/extractors/embedding_symbol.py
```

MacBook smoke:

```bash
export HF_HUB_DISABLE_XET=1
export PALACE_QODO_LOCAL_FILES_ONLY=false
export PALACE_EMBEDDING_BATCH_SIZE=8
export PALACE_EMBEDDING_MAX_SYMBOLS=256

# bring up MCP/Neo4j per local runbook
# preload Qodo model
# run symbol_index_swift + dead_code + embedding_symbol for bitcoin-core
# query Neo4j counts
# call palace.code.semantic_search
```

## Open Questions

- Should the bounded smoke write a distinct `IngestRun` metadata field for
  `max_symbols_applied`, or is the transcript count enough for G0.5.6?
- Do we want a temporary smoke-only backend option for deterministic fake
  embeddings, or should G0.5.7 require Qodo-only evidence?
- Should full `uw-ios-app` embedding population be a separate G0.5.8
  operational slice after small-kit smoke passes?

## Roadmap Position After This Work

If this readiness work lands and MacBook smoke passes:

- `G0.5.6` can close when all five target projects have at least bounded
  embedding counts and the cascade transcript is attached.
- `G0.5.7` can close when semantic search top-3 manual relevance evidence is
  attached.

Remaining roadmap after G0.5:

1. `G1` capability audit and four-column baseline: Gimle / SymDex /
   Sourcegraph Amp / grep.
2. `G2` recipe pilot with synthetic and real PR corpus.
3. `G2.5` domain-preflight middleware enforcement.
4. `G3` gaming-resistant measurement loop.
5. `G4` rollout to four more recipe types.
6. `G0f` security foundation before any external pilot.
7. `G5` optional extractors only after metric trigger.
