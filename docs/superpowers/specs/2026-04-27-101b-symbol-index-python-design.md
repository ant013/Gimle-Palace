---
slug: 101b-symbol-index-python
status: rev1 (depends on 101a foundation merge)
branch: feature/101b-symbol-index-python (cut from develop AFTER 101a merge)
paperclip_issue: GIM-102
predecessor: bb0e944
date: 2026-04-27
parent_initiative: N+2 Extractor cycle — first real content extractor
related: 101a (foundation, MUST be merged first), GIM-100 (D1-D9)
depends_on: 101a (hard gate)
---

# Slice 101b — Symbol Index Python (first real content extractor)

## Goal

Ship the **first real content extractor** built on top of merged 101a foundation. Reads pre-generated `.scip` files (produced by `npx @sourcegraph/scip-python` outside the container) for Python codebases, ingests via 3-phase bootstrap into Tantivy + Neo4j shadow, exposes `palace.code.find_references` composite tool with 3-state distinction (never-indexed / indexed-then-evicted / indexed-zero-refs).

Validation: dogfood on Gimle-Palace's own Python codebase. Subsequent slices (102 TS/JS, 103 Kotlin/Swift) follow same pattern with ~2-3 day cadence per language.

## Sequence

Second slice in N+2 Extractor cycle. **HARD DEPENDENCY: 101a must merge to develop first.** This slice's branch cut from post-101a-merge develop tip.

## Hard dependencies

- **101a foundation slice merged on develop** (provides: TantivyBridge async context manager, BoundedInDegreeCounter with run_id, ensure_custom_schema, eviction policy, IngestCheckpoint, SymbolOccurrenceShadow, error_code enum, hard circuit breaker)
- ResearchAgent + Opus reviews on GIM-100 — done
- 101a Settings has `palace_scip_index_paths: dict[str, str]` config

## Non-goals

- Foundation work (lives in 101a)
- TS/JS/Kotlin/Swift/Rust/Solidity/FunC/Anchor extractors — Slices 102+
- `palace.code.semantic_search` — Slice 5 deferred from N+2 Cat 1
- scip-python multi-stage Dockerfile (Option a from rev2) — defer; Option b accepted (operator runs scip-python outside container, passes `.scip` path)

## Architecture

### scip-python integration — pre-generated `.scip` (D5 Option b)

Operator workflow:
```bash
# Outside container, on operator machine:
cd /repos/<project>
npx @sourcegraph/scip-python index --output ./scip/index.scip
# Mount path visible inside palace-mcp container as /repos/<project>/scip/index.scip
```

Container reads `.scip` via `palace_scip_index_paths` Settings dict (defined in 101a Settings):

```python
class FindScipPath:
    @staticmethod
    def resolve(project: str, settings: Settings, override: str | None = None) -> Path:
        """Resolve .scip file path for project. Per-call override > Settings dict.

        Raises ScipPathRequiredError (error_code: scip_path_required) if neither.
        """
        if override is not None:
            return Path(override)
        path = settings.palace_scip_index_paths.get(project)
        if path is None:
            raise ScipPathRequiredError(
                project=project,
                action_required=(
                    f"Set PALACE_SCIP_INDEX_PATHS env var to JSON dict including "
                    f"'{project}' key, or pass scip_path argument to "
                    f"palace.ingest.run_extractor"
                ),
            )
        return Path(path)
```

### SCIP parser — pip install scip + 250 MiB CI fixture (Python-pro F-J fix)

```python
# pyproject.toml additions:
# dependencies:
#   scip>=0.4.0  # Sourcegraph SCIP Python bindings; verified on PyPI
#   protobuf>=4.25  # recursion-depth DoS fix; raises message-size cap on upb backend

import scip.scip_pb2 as scip_pb2
from google.protobuf.message import DecodeError

def parse_scip_file(path: Path, max_size_mb: int = 500, timeout_s: int = 60) -> scip_pb2.Index:
    """Parse SCIP protobuf with size + timeout guards.

    Python-pro F-J fix: protobuf default Python backend caps at ~64 MiB,
    upb (C extension) backend used by protobuf>=4.0 caps at ~2 GiB. Pinned
    protobuf>=4.25 for recursion-depth DoS fix. CI test verifies 250 MiB
    decode round-trip.
    """
    size = path.stat().st_size
    if size > max_size_mb * 1024 * 1024:
        raise ScipFileTooLargeError(
            path=path,
            size_mb=size // (1024 * 1024),
            cap_mb=max_size_mb,
        )
    data = path.read_bytes()
    index = scip_pb2.Index()
    try:
        # ParseFromString returns bytes_consumed; raises DecodeError on failure
        index.ParseFromString(data)
    except DecodeError as e:
        raise ScipParseError(path=path, cause=str(e)) from e
    return index
```

### `SymbolIndexPython` extractor

Uses 101a substrate. Lifecycle:

```python
class SymbolIndexPython(BaseExtractor):
    name = "symbol_index_python"
    description = "Ingest Python symbols + occurrences from pre-generated SCIP file"

    async def extract(self, ctx: ExtractorContext) -> ExtractorStats:
        # 1. ensure_custom_schema (idempotent; from 101a)
        await ensure_custom_schema(ctx.driver)

        # 2. Pre-flight budget check (101a circuit breaker)
        await _preflight_budget_check(ctx.driver, ctx.group_id)

        # 3. Resolve .scip path
        scip_path = FindScipPath.resolve(
            project=ctx.project, settings=ctx.settings, override=ctx.scip_path_override
        )

        # 4. Parse SCIP file (size+timeout-bounded)
        scip_index = parse_scip_file(scip_path)
        symbols = list(_iter_scip_occurrences(scip_index))

        # 5. Counter first-pass (USE-only)
        counter = BoundedInDegreeCounter()
        counter_path = Path(ctx.settings.palace_tantivy_index_path) / "in_degree_counter.json"
        if not counter.from_disk(counter_path, expected_run_id=ctx.run_id):
            # Hard-fail per 101a F-D — refuse to start unless reset flag
            if os.environ.get("PALACE_COUNTER_RESET") != "1":
                return _error_envelope(ExtractorErrorCode.COUNTER_STATE_CORRUPT)
            counter = BoundedInDegreeCounter()  # explicit reset
        for s in symbols:
            if s.role == SymbolKind.USE:
                counter.increment(s.symbol_string)

        # 6. 3-phase bootstrap (per D6)
        async with TantivyBridge(
            Path(ctx.settings.palace_tantivy_index_path),
            heap_size_mb=ctx.settings.palace_tantivy_heap_mb,
        ) as bridge:
            phase1_count = await self._ingest_phase(
                symbols=[s for s in symbols if s.role in (SymbolKind.DEF, SymbolKind.DECL)],
                bridge=bridge, counter=counter, ctx=ctx, phase="phase1_defs",
            )
            await bridge.commit_async()
            await self._write_checkpoint(ctx, phase="phase1_defs", count=phase1_count)
            await _check_budget_at_phase_boundary(ctx.driver, ctx.group_id, ctx.settings.palace_max_occurrences_total)

            # Phase 2 conditional (D6)
            phase2_count = 0
            if await self._budget_remaining(ctx) > 0.5:
                phase2_count = await self._ingest_phase(
                    symbols=[s for s in symbols if s.role == SymbolKind.USE],
                    bridge=bridge, counter=counter, ctx=ctx, phase="phase2_user_uses",
                    importance_threshold=ctx.settings.palace_importance_threshold_use,
                )
                await bridge.commit_async()
                await self._write_checkpoint(ctx, phase="phase2_user_uses", count=phase2_count)
                await _check_budget_at_phase_boundary(...)

            # Phase 3 — vendor uses (only on large machines)
            phase3_count = 0
            if await self._budget_remaining(ctx) > 0.3:
                phase3_count = await self._ingest_phase(
                    symbols=[s for s in symbols if s.role == SymbolKind.USE],
                    bridge=bridge, counter=counter, ctx=ctx, phase="phase3_vendor_uses",
                    importance_threshold=0.0, allow_vendor=True,
                )
                await bridge.commit_async()
                await self._write_checkpoint(ctx, phase="phase3_vendor_uses", count=phase3_count)

        # 7. Persist counter (with run_id)
        counter.to_disk(counter_path, run_id=ctx.run_id)

        return ExtractorStats(
            nodes_written=phase1_count + phase2_count + phase3_count,
            details={"phase1": phase1_count, "phase2": phase2_count, "phase3": phase3_count},
        )
```

### `palace.code.find_references` composite tool — 3-state distinction (Silent-failure F5 fix)

```python
@tool_decorator("palace.code.find_references", _DESC_FIND_REFERENCES)
async def palace_code_find_references(
    qualified_name: str,
    project: str | None = None,
    max_results: int = 100,
) -> dict[str, Any]:
    """Returns occurrences from Tantivy + 3-state distinction:
    - State A (genuinely zero refs): index ran successfully, symbol has no callers → empty + ok
    - State B (never indexed): no IngestRun exists for project → warning: project_not_indexed
    - State C (evicted): EvictionRecord exists for symbol → warning: partial_index + coverage_pct
    """
    cm_session = code_router.get_cm_session()
    if cm_session is None:
        handle_tool_error(RuntimeError("CM not started"))
        raise

    req = FindReferencesRequest(
        qualified_name=qualified_name,
        project=project,
        max_results=max_results,
    )
    resolved_project = req.project or _DEFAULT_CM_PROJECT

    # Step 1: check :IngestRun for project (Silent-failure F5 — never-indexed state)
    ingest_run = await _query_ingest_run(
        cm_session,
        project=resolved_project,
        extractor_name="symbol_index_python",
    )
    if ingest_run is None or not ingest_run.success:
        return {
            "ok": True,
            "occurrences": [],
            "total_found": 0,
            "warning": "project_not_indexed",
            "action_required": (
                f"Run palace.ingest.run_extractor('symbol_index_python', '{resolved_project}') "
                f"before relying on this answer"
            ),
        }

    # Step 2: search_graph for resolved Symbol — exact match first, then suffix fallback
    raw = await cm_session.call_tool("search_graph", {
        "project": resolved_project,
        "qn_pattern": f"^{re.escape(req.qualified_name)}$",
        "label": "Function|Method",
        "limit": 2,
    })
    matches = code_router.parse_cm_result(raw).get("results", [])
    if not matches:
        # Fallback: suffix match
        raw = await cm_session.call_tool("search_graph", {
            "project": resolved_project,
            "qn_pattern": f".*\\.{re.escape(req.qualified_name)}$",
            "label": "Function|Method",
            "limit": 2,
        })
        matches = code_router.parse_cm_result(raw).get("results", [])

    if not matches:
        return {
            "ok": False,
            "error_code": "symbol_not_found",
            "requested_qualified_name": req.qualified_name,
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "error_code": "ambiguous_qualified_name",
            "matches": [{"qualified_name": m["qualified_name"]} for m in matches],
        }

    resolved = matches[0]
    sym_id = symbol_id_for(resolved["qualified_name"])

    # Step 3: Tantivy term query (async-wrapped)
    tantivy_bridge = _get_tantivy_bridge()
    occurrences = await tantivy_bridge.search_by_symbol_id_async(
        sym_id, limit=req.max_results + 1
    )
    truncated = len(occurrences) > req.max_results
    occurrences = occurrences[: req.max_results]

    # Step 4: check :EvictionRecord for warning (state C)
    eviction_info = await _query_eviction_record(
        cm_session,
        qualified_name=resolved["qualified_name"],
        project=resolved_project,
    )

    response = {
        "ok": True,
        "requested_qualified_name": req.qualified_name,
        "qualified_name": resolved["qualified_name"],
        "project": resolved_project,
        "occurrences": occurrences,
        "total_found": len(occurrences) + (1 if truncated else 0),
        "truncated": truncated,
    }
    if eviction_info:
        response["warning"] = "partial_index"
        response["eviction_note"] = (
            f"{eviction_info['total_evicted']} occurrences evicted "
            f"(round={eviction_info['eviction_round']}); coverage incomplete"
        )
        response["coverage_pct"] = int(
            100 * len(occurrences) / (len(occurrences) + eviction_info["total_evicted"])
        )
    return response
```

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | scip-python integration probe: generate `.scip` outside container via `npx @sourcegraph/scip-python` on Gimle-Palace's own Python codebase; verify decode via `pip install scip` + `scip_pb2.Index.FromString` round-trip | PE | 101a merged |
| 2 | `parse_scip_file(path, max_size_mb=500, timeout_s=60)` with size + protobuf DoS limits; CI fixture: 250 MiB synthetic .scip decode round-trip green; pin `protobuf>=4.25` and `scip>=0.4.0` in pyproject.toml | PE | T1 |
| 3 | `FindScipPath.resolve()` resolver from Settings dict + per-call override; raises `ScipPathRequiredError` (error_code: scip_path_required) when missing | PE | 101a merged |
| 4 | `SymbolIndexPython` extractor full impl using 101a substrate (TantivyBridge async cm, BoundedInDegreeCounter with hard-fail, ensure_custom_schema, eviction, IngestCheckpoint, circuit breaker); 3-phase bootstrap with proper checkpoint reconciliation; unit tests + integration test using real `.scip` from T1 | PE | T1, T2, T3 |
| 5 | `palace.code.find_references` composite tool: 3-state distinction (project_not_indexed via :IngestRun lookup, partial_index via :EvictionRecord, genuinely zero refs); blake2b symbol_id; exact-match-first + suffix fallback; integration test via streamablehttp_client (per GIM-91 wire-contract) verifies all 3 states | PE | T4 |
| 6 | Documentation: README symbol-index extractor section; CLAUDE.md operator workflow ("run scip-python outside container, set PALACE_SCIP_INDEX_PATHS"); spec acceptance #12 (latency caveat already in 101a) | PE | T1-T5 |
| 7 | CR Phase 3.1 mechanical review | CR | T6 |
| 8 | Opus Phase 3.2 adversarial review (focus: scip parser robustness, find_references 3-state correctness, dogfood validity) | Opus | T7 |
| 9 | QA Phase 4.1 live smoke on iMac: 101a foundation already deployed; place `.scip` for Gimle-Palace at configured path; run `palace.ingest.run_extractor("symbol_index_python", "gimle")`; verify Symbol count + Tantivy doc count + `palace.code.find_references("register_code_tools")` returns ≥1 occurrence; all 3 states reachable via test calls (genuine-zero, never-indexed by querying unrun project, partial via synthetic eviction) | QA | T8 |
| 10 | Phase 4.2 squash-merge — CTO only | CTO | T9 |

## Acceptance

1. `pip install scip` + `protobuf>=4.25` pinned; CI fixture 250 MiB decode round-trip green.
2. `parse_scip_file` enforces size cap (500 MB default) + timeout (60s); raises structured error envelopes for too-large / parse-failed.
3. `FindScipPath.resolve` returns Path or raises ScipPathRequiredError with actionable message; verified via unit test for missing project.
4. `SymbolIndexPython` extractor green on Gimle-Palace's `.scip`: writes ≥500 :Symbol nodes (defs+decls) + ≥5K :SymbolOccurrenceShadow + Tantivy docs after Phase 1+2; IngestCheckpoint records each phase with expected_doc_count.
5. Restart-survivability dogfood: kill container after Phase 1 commit, restart, query `find_references` → no duplicates (verified by 101a's doc_key uniqueness + this slice's actual ingestion path).
6. `palace.code.find_references` 3-state distinction:
   - State A (genuinely zero): query symbol with no callers → returns `ok: true, occurrences: [], total_found: 0` with no warning
   - State B (never indexed): query against project that hasn't been indexed → `warning: project_not_indexed` + action_required
   - State C (partial): query symbol with EvictionRecord → `warning: partial_index` + coverage_pct
7. MCP wire-contract test (per GIM-91): all 3 states reachable via real streamablehttp_client.
8. Pattern #21 dedup-aware registration: `palace.code.find_references` appears in `tools/list` exactly once.
9. CR Phase 3.1 + Opus Phase 3.2 reviews passed; QA Phase 4.1 live smoke green.

## Out of scope

- All 101a foundation work (already shipped)
- TypeScript / JavaScript / Kotlin / Swift / Rust / Solidity / FunC / Anchor extractors — Slices 102+
- Multi-stage Dockerfile for in-container scip-python — defer; Option b accepted

## Decisions recorded (rev1, post-101a)

This slice realizes the Python-extractor-specific portion of the 26 round-2 findings; foundation-level fixes are in 101a. Specifically:

| Round 2 Finding | This slice |
|---|---|
| Silent-failure F5 find_references 3-state | T5 implements 3-state distinction (project_not_indexed via :IngestRun lookup) |
| Silent-failure F8 scip_path None | T3 ScipPathRequiredError with actionable message |
| Python-pro F-J protobuf 200 MiB cap | T2 CI fixture for 250 MiB decode + protobuf>=4.25 pin |
| Architect F3 multi-project paths | T3 uses Settings.palace_scip_index_paths dict (defined in 101a) |

## Open questions

1. `npx @sourcegraph/scip-python index` invocation outside container — operator UX. Should `palace.ops` provide a helper that shells out for the operator? Defer to v2 unless friction surfaces.
2. `.scip` file freshness vs git commit. If operator runs scip-python on commit X, then makes commit Y, ingest reads stale `.scip`. Detect via commit_sha mismatch in :IngestRun? Defer to followup.
3. Multi-Python-version support. scip-python has Python 3.8+ requirement; what if operator's project is 3.7? Defer; add to README compatibility matrix.

## References

- 101a foundation spec (sibling)
- `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` — D1-D9
- pip install scip: pypi.org/project/scip/
- SCIP proto: github.com/sourcegraph/scip/blob/main/scip.proto
- @sourcegraph/scip-python: npmjs.com/package/@sourcegraph/scip-python
- GIM-91 — MCP wire-contract test rule
- GIM-94 — Phase 4.2 CTO-only rule
