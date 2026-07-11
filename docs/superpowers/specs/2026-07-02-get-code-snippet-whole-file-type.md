# `get_code_snippet` — `scope=symbol|file|type` (fix extension truncation)

**Date:** 2026-07-02
**Author:** Anton + Claude (Board)
**Status:** Design **v2** — voltAgent panel (architect / code / silent-failure) folded in; two panel claims overridden by live-graph evidence (noted inline). Ready to plan.
**Component:** `services/palace-mcp/src/palace_mcp/code/native_get_code_snippet.py`, `snippet_provider.py`, new `snippet_scope.py`, `memory/constraints.py`, `code_router.py`.

## Problem

`get_code_snippet(qualified_name, project)` returns a narrow window around a **single** `:Symbol`. For a Swift `class Foo {…}` whose conformance/logic lives in a separate `extension Foo: P {…}` (ubiquitous Swift pattern, often in another file), it returns only the class window and **silently drops the extensions** — the caller believes they saw the whole type when they did not (2026-07-01 A/B: "class, lines 1–50"; the `sendData`/`send` conformance in the extension was absent, forcing a serena/`Read` fallback).

## Root cause (verified against LIVE graph 2026-07-02)

1. **`:Symbol` has `line_start` (100% coverage) but NO `line_end`.** Live: evm-kit `44717/44717` symbols carry `line_start`, `0` carry `line_end`. (⚠️ Panel finding "line_start is never written / symbol path returns file_head" is **refuted by live data** — it reasoned from stale fixtures + a source grep that missed the writer. The real degraded path is the ±window below, not file_head.)
2. `_LOOKUP_SYMBOL` selects `s.line_end` → always `NULL`; `_window_bounds` (`native_get_code_snippet.py:118-125`) therefore returns `[line_start-20, line_start+40]` — a **fixed ±window** (`snippet_quality="approximate_window"`), never the type's real extent.
3. **Extensions are not distinct symbols.** Live evm-kit `kind` set = `{method, parameter, property, initializer, unspecifiedkind, typealias, struct, enum, function, class, protocol}` — **no `extension` kind**, and **`EXTENSION_OF` edges = 0** on both evm and uw. (⚠️ Panel finding "traverse the existing `EXTENSION_OF` edge as primary" is **not viable on current data** — the native `palace-swift-scip-emit` does not tag `Extension` symbols, so `scip_parser.py:298` never fires. Enabling it needs an emitter change + full re-ingest → tracked as a fast-follow, NOT this slice.)
4. But extension **members** mangle under the base type's moniker, so an extension method's `qualified_name` **STARTS WITH the base type moniker** and is discoverable that way, including across files. Swift length-prefixed mangling makes the type moniker a safe prefix (panel `code` proved: siblings `11WalletStoreC` vs `18WalletStoreManagerC` don't collide; private `LL` and generic suffixes append *after* the type moniker; nested types are included-by-design).

Net: no single symbol span covers a type + its extensions; `line_end` is absent; `EXTENSION_OF` is absent. **Moniker-prefix grouping (guarded by `module_name`) is the only mechanism available on current data.**

## Goals

Two opt-in scopes, **default behavior byte-identical**:
- **`scope="file"`** — return the whole file the resolved symbol lives in (up to a cap, truncation always flagged with counts).
- **`scope="type"`** — return the type's declaration **plus every file holding its members/extensions**, found by moniker-prefix. Solves the class+extension pattern natively.

Non-goals: precise brace-accurate sub-file spans (needs `line_end`, deferred to Q4 fast-follow); `EXTENSION_OF` traversal (needs emitter change); embedding/audit changes.

## API

Add one optional, validated param:
```
scope: "symbol" | "file" | "type"  = "symbol"
```
- Enum, not booleans (panel-architect endorsed): `file`/`type` mutually exclusive by construction.
- **Must be explicitly validated** — an unrecognized value returns `validation_error`, NOT a silent default (today `native_get_code_snippet(**_)` at `:160` + the arg-splat in `code_router.py:362` would swallow it → silent no-op, exactly the failure class we're killing). Make `scope` a named param.
- Advertise it in `_open_schema_for_tool` (`code_router.py:147-156`) as an enum with default `"symbol"` for MCP discoverability (schema is `additionalProperties:true`, so no breakage for omitters).
- `scope="symbol"` executes today's exact path → **byte-identical output** (regression-tested).

## Response contract (silent-failure-hardened — panel `silent-failure` mandate)

Every truncation, drop, downgrade, or possible incompleteness MUST be a **structured, top-level, machine-detectable flag/count** — never a bare boolean, a free-text `note`, or a field reachable only inside an optional array.

**Top-level (always present for `file`/`type`; unchanged/omitted for `symbol`):**
```jsonc
{
  "qualified_name": "...", "requested_qualified_name": "...", "project": "...",
  "requested_scope": "type", "effective_scope": "type",      // differ ⇒ downgrade happened
  "scope_downgraded": false, "downgrade_reason": null,
  "snippet_quality": "whole_type",                            // + "whole_type_partial" when complete=false
  "complete": true,                                           // false if ANY: doc error | truncation | best_effort type
  "type_completeness": "best_effort",                         // always best_effort (moniker heuristic, no EXTENSION_OF)
  "completeness_note": "moniker-prefix grouping; extensions with divergent monikers or off-disk files may be absent",
  "documents_total": 2, "documents_failed": 0, "documents_truncated": 0,
  "dropped_files": [],                                        // PATH LIST (not a count) when _MAX_TYPE_FILES hit
  "deprecated_extensions_suppressed": 0,                      // count filtered by NOT :Deprecated (when include_deprecated=false)
  "documents": [ /* see below */ ]
  // NOTE: no top-level start_line/end_line/source for file/type — meaningless across files, and populating
  // from doc[0] re-creates the original bug (caller reads declaration file, thinks type is complete).
}
```
For `scope="symbol"` and `scope="file"` single-doc results the legacy top-level `source`/`start_line`/`end_line` remain (file scope has exactly one doc, so top-level == that doc — safe). `symbol` output stays byte-identical (no `documents`, no new fields).

**Per document:**
```jsonc
{ "file_path": "...", "start_line": 1, "end_line": 134, "total_lines": 134,
  "source": "…" /* nullable on error */, "truncated": false, "truncated_lines": 0,
  "truncated_reason": null /* "lines" | "bytes" */, "role": "declaration" /* |"extension"|"file" */,
  "error": null, "error_code": null }
```

## Design

### Resolution
- Extend `_LOOKUP_SYMBOL` RETURN to add `s.kind AS kind, s.module_name AS module_name` (panel: currently returns neither; both are needed). Exact/ambiguous handling unchanged; `scope="symbol"` path unchanged.
- **`scope="file"`**: take the resolved symbol's `file_path`, read the whole file (cap-aware), return one `documents[]` entry `role:"file"` + legacy top-level fields.
- **`scope="type"`**:
  1. **Language gate:** if resolved `language != "swift"` → `effective_scope="file"`, `scope_downgraded=true`, `downgrade_reason="whole_type is Swift-only (moniker model)"`, proceed as file scope. (Gate on resolved language from `snippet_provider` / file extension, NOT `module_name` — panel-architect #7.)
  2. **Member check:** if resolved `kind ∉ {class, struct, enum, protocol}` (note: no `actor`/`extension` in the live writer vocabulary — unmapped kinds fall here) → `effective_scope="file"`, `scope_downgraded=true`, `downgrade_reason="resolved symbol is a member; returned enclosing file"`. (Q1 = file-scope fallback for v1; upward mangling-trim deferred.)
  3. **File discovery (moniker-prefix, guarded):**
     ```cypher
     MATCH (m:Symbol)
     WHERE m.group_id = $group_id
       AND m.module_name = $module_name           -- belt-and-suspenders vs cross-module tail collision
       AND m.qualified_name STARTS WITH $type_qn
     RETURN DISTINCT coalesce(m.file_path, m.path) AS file_path,
            sum(CASE WHEN m:Deprecated THEN 1 ELSE 0 END) AS dep_count  -- for deprecated_extensions_suppressed
     ```
     (When `include_deprecated=false`, filter `NOT m:Deprecated` for the returned set but still COUNT suppressed ones.)
  4. Order: declaration file (resolved symbol's `file_path`) first, then remaining lexicographically (documented as arbitrary — `dropped_files` therefore lists real paths, no "nearest" claim).
  5. Each file → one whole-file `documents[]` entry (`role`: declaration file = `"declaration"`, others = `"extension"`).

### Multi-doc assembly → new module
Put fan-out/ordering/caps/budget/per-doc-error handling in **`code/snippet_scope.py`** (`assemble_scope_documents(session, resolved_row, scope, *, repo_path, caps) -> ScopeResult`), the multi-file analog of `snippet_provider.py`. `native_get_code_snippet.py` keeps resolution + dispatch only (panel-architect #5). Enables unit tests without a live graph.

### `resolve_snippet` changes (panel BLOCKER — whole-file is a lie today)
`snippet_provider.py:27-28` already hard-caps **200 lines / 16 KB** on every read. Reusing it as-is silently truncates every "whole file". Changes:
- Add params `max_lines: int | None = None`, `max_bytes: int | None = None` (default `None` → today's 200/16 KB, preserving the semantic-search hydration path byte-for-byte). Whole-file/type callers pass `_WHOLE_FILE_MAX_LINES=1200`, per-doc `max_bytes` from the running budget.
- `line_end=None` already reads to EOF (`:110`) then caps — the real work is honoring the larger cap.
- Return **`total_lines`** (real file length) and **`truncated_reason`** (`"lines"|"bytes"`) on `SnippetResult`, and **`truncated_lines`** (dropped count) — so a bare `truncated=true` is never the only signal (panel: flag+count required). `end_line` clamped to the last fully-included line when byte-cap fires.
- **`_check_stale`** (`:150-167`) currently `except Exception: return False` → reports `stale=false` on an *error* (false assurance). Change to surface `stale=None`/`stale_check_failed=true` when the check errors, distinct from a real `stale=false` (panel silent-failure #7).
- Guard empty file → `start_line=1, end_line=0/None, total_lines=0` documented (avoid inverted range).

### Caps / budget (owned by `snippet_scope`, not `resolve_snippet`)
- `_WHOLE_FILE_MAX_LINES = 1200`, `_WHOLE_FILE_MAX_BYTES = 64_000` per doc, `_MAX_TOTAL_BYTES = 400_000` across docs, `_MAX_TYPE_FILES = 12`.
- `snippet_scope` seeds `remaining_bytes = _MAX_TOTAL_BYTES`; each doc gets `max_bytes = min(remaining, _WHOLE_FILE_MAX_BYTES)`; on exhaustion, stop and record remaining files in `dropped_files` (path list) + `complete=false`.
- Cap precedence: lines first, then bytes; `end_line` clamped to last full line.
- Per-doc read failure (dependency/off-disk/deleted) → that doc gets `source=null, error, error_code`, loop continues, and top-level `documents_failed++`, `complete=false`.

### Performance (panel MAJOR — mandatory for v1)
No index on `Symbol.group_id` or `Symbol.qualified_name` (`constraints.py:33-40`, `cypher.py:19-26` index only `Project`/`Bundle`/`AnalysisRun`). Both `_LOOKUP_SYMBOL` and the type-file query do full `:Symbol` label scans; on uw (248 k) a `whole_type` call = two full scans, uncached. The evm "~2 s" does not generalize.
- Add composite **range** index: `CREATE INDEX symbol_group_qn IF NOT EXISTS FOR (s:Symbol) ON (s.group_id, s.qualified_name)` in `constraints.py`. Range index makes `group_id =` + `qualified_name STARTS WITH` index-backed (STARTS WITH is a range predicate) — also speeds the existing `_LOOKUP_SYMBOL`. Benchmark `whole_type` on uw before merge; record the number.

## Files
- **Create:** `code/snippet_scope.py` (assembly + caps + budget + per-doc errors); `tests/code/test_native_get_code_snippet_scope.py`.
- **Modify:** `native_get_code_snippet.py` (add validated `scope`; extend `_LOOKUP_SYMBOL` RETURN `kind,module_name`; dispatch to `snippet_scope`; keep symbol path byte-identical). `snippet_provider.py` (`max_lines`/`max_bytes` params; `total_lines`/`truncated_lines`/`truncated_reason`; `_check_stale` unknown signal; empty-file guard). `memory/constraints.py` (index). `code_router.py` (advertise `scope` enum).

## Test matrix (panel-expanded)
(a) same-file extension → one doc covers both; (b) **cross-file** extension → ≥2 docs, extension file present; (c) large file >1200 lines → `truncated`, `truncated_lines`, `total_lines` correct, `truncated_reason="lines"`; (d) dependency-scope symbol → per-doc `error` set, `complete=false`, call still returns; (e) **`scope="symbol"` byte-identity regression** vs current output; (f) line-cap boundary 1200/1201; (g) total-byte budget exhaustion across 3+ docs → `dropped_files` populated (path list), `complete=false`; (h) non-Swift symbol + `scope="type"` → `effective_scope="file"`, `scope_downgraded=true`; (i) member symbol + `scope="type"` → file downgrade flagged; (j) empty file whole-file → no inverted range; (k) `ambiguous_qualified_name` under `file`/`type` → unchanged error; (l) unknown `scope` value → `validation_error`; (m) nested-type inclusion asserted (documented behavior).

## Open questions resolved by the panel
- **Q1** member→type: **file-scope fallback (flagged)** for v1; defer upward mangling-trim (fragile with generics).
- **Q2** whole-files for `type`: **yes** (no `line_end`).
- **Q3** `documents[]`: **always for `file`/`type`, omit for `symbol`** (byte-identity).
- **Q4** add `line_end` at ingest: **fast-follow, now cheaper than the panel thought** — `line_start` already exists at 100%, so this is "add `line_end` from the SCIP def range" only; it fixes the default `symbol` ±window too. Separate slice.

## Fast-follows (NOT this slice)
- Emit `Extension`-kind symbols in `palace-swift-scip-emit` so `EXTENSION_OF` edges materialize; then switch `whole_type` file-discovery to edge-traversal (authoritative) with moniker-prefix as fallback.
- Add `:Symbol.line_end` (Q4) → precise spans + fixes `symbol` scope default.
- Apply the multi-doc shape to `get_snippet_rich`.
