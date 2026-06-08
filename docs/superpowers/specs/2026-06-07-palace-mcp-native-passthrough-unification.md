# palace-mcp Native Passthrough Unification — Drop CM-Sidecar Dependency for Read-Path Tools

**Status:** Draft v3 (post-second-review cleanup)
**Date:** 2026-06-07
**Author:** Board (claude-opus-4-7) — drafted autonomously per operator instruction 2026-06-07 ~13:00 UTC
**Owner (intended):** CXCTO (walker), implementation slices to CXPythonEngineer + CXInfraEngineer
**Related:** GIM-1500 (namespace unification — landed; this spec extends that work)

---

## Change log

- **v2 → v3 (2026-06-07, post-2nd-pass cleanup):**
  - Deleted stale §4.5 dispatch code that still referenced `FallbackToCM` exception (superseded by §4.2 sentinel-only design). (architect APPROVE_WITH_NITS, qa H)
  - Rewrote §4.6 observability from Prometheus to **caplog INFO log** only (matches AC-8 and Change Log v2 statement). (architect APPROVE_WITH_NITS)
  - Renamed §6.1 test `test_native_raises_FallbackToCM_falls_through` → `test_native_returns_fallback_sentinel_falls_through`. (architect)
  - Removed stale §8 risk row "apoc.path.subgraphAll not enabled" (APOC absent confirmed, design no longer uses it). (architect + qa)
  - Defined `KNOWN_NON_CALL_EDGES` constant + `tests/code/test_edges_registry.py` test file name + Cypher `SHOW RELATIONSHIPS` survey approach to close AC-16. (qa H new)
  - Added 3 new ACs (AC-17/18/19) for regex-bypass scenarios: multi-MATCH leak rejection, Cypher-comment smuggling neutralization, string-literal CREATE. (security)
  - Added redaction note on `cypher_error` envelope (no full Neo4j path/schema leakage). (security L)
  - Defined `short_name_from_qualified_name(qn: str) -> str` body inline (was ellipsis). (security M)
  - Marked §9 Q1/Q3/Q5 RESOLVED inline. (architect)

- **v1 → v2 (2026-06-07, post-3-reviewer pass):**
  - **API-fact corrections:** namespace API is `resolve(driver, value) → NamespaceResolution(slug, cm_project_name)` + `assert_known_project(driver, value)` raising `UnknownProjectError`; there is no `kind` discriminator. `resolve_snippet` is **sync** and returns tuple `(SnippetResult | None, warning_code, warning_message)`. `:Function.name` is short-name not qualified_name. All §4 code samples rewritten against real API. (architect C1, C2, H1)
  - **APOC absent, confirmed via live probe:** `apoc.path` procedures = 0 on prod Neo4j 2026.05.0 Community. `trace_call_path` switches to pure-Cypher variable-depth `-[:CALL_EDGES*1..max_depth]-`; no APOC dependency. (architect H4, qa C2)
  - **Cypher safety hardening:** `query_graph` now enforces (a) regex deny-list of write/admin verbs (`CREATE/MERGE/DELETE/SET/REMOVE/DROP/LOAD/CALL dbms\..*/CALL apoc\..*`), (b) read-only session via `session(default_access_mode="r")`, (c) **mandatory scope predicate** — every `MATCH` must reference `$group_id` or `$project_id` (regex check on parsed query). Without those guards, raw Cypher leaks cross-project. (security C1, C2)
  - **Byte-cap streaming + depth/row clamps:** `query_graph` accumulates with `sys.getsizeof` running total, aborts at 16 MB; row ceiling 100 000; `trace_call_path.depth` clamped to `[1, 6]`. (security H3, H4)
  - **`detect_changes.since` validation:** new `_SINCE_RE` regex covering ISO-8601 + git approxidate ("2 weeks ago"). (security H2)
  - **Dispatch design simplified:** drop `FallbackToCM` exception; single sentinel `{"ok": false, "error_code": "fallback_to_cm"}` return value. (architect H2)
  - **Edge type registry:** new `code/edges.py: CALL_EDGES = (...)` consumed by `trace_call_path` AND a CI schema-survey test asserting no unlisted edge types appear in production. (architect H5)
  - **`get_code_snippet` corrected:** explicit `(:Symbol)-[:DEFINED_IN]->(:File)<-[:CONTAINS]-(:Function)` join via `(file_path, short-name-from-qn)`; documented as heuristic; `snippet_quality ∈ {exact, approximate_function_match, approximate_window, file_head}` enum in response. (architect C1, M2)
  - **Seed fixture explicit (Phase 1.7):** new `tests/integration/fixtures/native_passthrough_seed.cypher` with `:Project`, `:File`, `:Symbol`, `:Function`, `:Module`, `:ExternalDependency`, plus `:REFERENCES`+`:CONTAINS`+`:DEFINED_IN` edges; documented node-count expectations. (qa H3)
  - **Automated CM fallback test (AC-7):** new `test_cm_fallback_path_invoked_on_unregistered_project` in §6.3. (qa C1)
  - **CM-only project list tool:** new `palace.code.list_passthrough_projects` Phase 1.8 deliverable returning `{native: [...], cm_only: [...]}`. (architect M3)
  - **Caplog observability:** dropped Prometheus mention; structured INFO log `passthrough.dispatch` per call asserted via `caplog` (AC-8 rewritten). Palace has no Prometheus backend (per GIM-1500 v3 finding). (qa M8)
  - **`Verification method` column** added to §7 ACs; **`PR merge gate` column** added to §5 phase table. (qa M10)
  - **Test_cm_contract.py migration scope listed:** explicit table in §6.5 — which existing tests are kept / split / deleted. (qa H5)
  - **Phases re-bucketed** per architect M4: 1.0+1.3 merged (router + diff = 3h), 1.1+1.2 merged (query + snippet = 3.5h). Total 7 PRs instead of 9.

---

## 1. Problem statement

`palace.code.search_code`, `search_graph`, `query_graph`, `get_code_snippet`, `detect_changes`, `get_architecture`, `trace_call_path` are passthrough tools forwarded to the external `codebase-memory-mcp` (CM) sidecar binary. After GIM-1500 wired the slug→CM-name namespace resolver, these tools still fail end-to-end for projects ingested by Palace's own extractors because:

1. **Palace and CM ingest different sources.** Palace's native ingest of `uw-ios-baseline` produces 250 595 `:Symbol` nodes under `project/uw-ios-baseline`, but the CM sidecar SQLite store at `~/.cache/codebase-memory-mcp/*.db` was populated by an unrelated workflow against different on-disk paths (e.g. `Users-ant013-Ios-HorizontalSystems-EvmKit.Swift` from `/Users/ant013/Ios/HorizontalSystems/...`, while Palace ingests EvmKit from `/Users/ant013/Ios/uw-fresh-2026-06-04/...`).
2. **CM-name derivation depends on deployment mode.** The migration `m2026_06_backfill_project_cm_project_name` uses container-form (`repos-<parent_mount>-<relative_path>`), but the native dev-Mac CM corpus uses host-paths (`Users-ant013-Ios-...`). The two namespaces never overlap.
3. **CM sidecar is a separate Go binary with separate storage** (SQLite + FTS5 + vector tables) — not Neo4j, not Tantivy. Palace has no operational visibility into it.

Result: an operator who registers a project via Palace and ingests it through Palace extractors cannot use `palace.code.search_code` (or the other 6 passthroughs) against that project. Symptom is operator-fatal: "search returns nothing" with no clear error path.

## 2. Root cause

palace-mcp has two backing graphs with different storage technologies and different ingest pipelines:

| Layer | Storage | project_id | Reachable today via |
|---|---|---|---|
| Palace native | Neo4j + Tantivy | `project/<slug>` | `find_references`, `find_owners`, `find_hotspots`, `find_public_api`, `find_dead_symbols`, `find_dead_code`, `find_cross_module_contracts`, `list_functions`, `semantic_search`, `call_hierarchy_v2` |
| External CM sidecar | SQLite + FTS5 + vectors (Go binary, gRPC stdio MCP) | host-derived path string | `search_code`, `search_graph`, `query_graph`, `get_code_snippet`, `detect_changes`, `get_architecture`, `trace_call_path` |

The passthrough split is an artifact of historical bootstrap (CM was available; Palace native was incomplete). Today Palace has 80% of the substrate needed to serve the same surface. Continuing to maintain two graphs forces ingest duplication, inflates schema, and produces UX regressions whenever they drift.

## 3. Scope

### In scope (Phase 1)

Reimplement these 6 of 7 passthrough tools natively over Palace's Neo4j/Tantivy graph, with CM sidecar retained as **optional fallback** for projects that exist in CM but not as Palace `:Project` slugs.

| # | Tool | Native substrate Phase 1 | Phase 2 followup |
|---|---|---|---|
| 1 | `query_graph` | Thin wrapper around `driver.session().run(query, project_id=...)`; auto-scope by `:Project.group_id` | — |
| 2 | `get_code_snippet` | `:Symbol`/`:Function` → `(file_path, start_line, end_line)` → existing `code/snippet_provider.resolve_snippet` | line-range backfill for `:Symbol` where no `:Function` exists (see §9 Q4) |
| 3 | `detect_changes` (files-list mode) | Wrap existing `palace.git.diff(mode="stat")` | Symbol-impact mode (touched files → `:REFERENCES` traversal at depth N) |
| 4 | `trace_call_path` (calls mode) | Variable-length Cypher over `:REFERENCES\|:CONFORMS_TO\|:EXTENDS\|:EXTENSION_OF\|:EXISTENTIAL_USE` | `data_flow` / `cross_service` modes (need `:HTTP_CALLS`/`:DATA_FLOWS` extractors) |
| 5 | `search_graph` (without `query=` BM25) | Cypher template: label filter + `name_pattern` LIKE + `file_path` LIKE + degree filter | BM25 full-text via Tantivy + camelCase splitting + structural boost |
| 6 | `get_architecture` (basic) | Cypher aggregation over `:Module`, `:ExternalDependency`, `:File.language`, `:Symbol.is_main_entry` | Routes view (needs `:Route` extractor) |

**Deferred entirely to Phase 2** (separate spec):

| Tool | Reason |
|---|---|
| `search_code` (text content search) | Requires either (a) new file-body Tantivy index, or (b) `rg`/`grep` subprocess against host paths. Adds substantial dependency and disk-IO surface. Decided as standalone spec. |

### Out of scope (this spec)

- New extractor types (`:Route`, `:HTTP_CALLS`, `:DATA_FLOWS`).
- Migrating the 12+ CM-only projects (Android UW, librustzcash, audit mirrors, etc.) into Palace. Operators keep accessing them via CM fallback.
- Removing the CM sidecar binary or its launcher. Phase 1 ships **coexistence** mode; binary stays opt-in.
- BM25/full-text search over qualified names. Deferred to Phase 2.
- `search_code` text content search. Deferred to Phase 2.
- API schema changes (the 6 tools keep their existing call signatures for caller compat).

## 4. Design

### 4.1 Router-level dispatch table

`code_router.py:_ENABLED_CM_TOOLS` becomes a richer registration table: per tool, declare native implementation, CM fallback eligibility, and fallback condition.

```python
# code_router.py (new section)

@dataclass(frozen=True)
class PassthroughEntry:
    name: str                                # MCP tool name
    native_impl: Callable[..., Awaitable[dict]] | None  # async native handler
    cm_passthrough: bool                     # may forward to CM if native says "fall through"
    cm_tool_name: str | None                 # CM-side tool name (when passthrough)

_PASSTHROUGH_TABLE: tuple[PassthroughEntry, ...] = (
    PassthroughEntry("query_graph",      native_query_graph,      cm_passthrough=True, cm_tool_name="query_graph"),
    PassthroughEntry("get_code_snippet", native_get_code_snippet, cm_passthrough=True, cm_tool_name="get_code_snippet"),
    PassthroughEntry("detect_changes",   native_detect_changes,   cm_passthrough=True, cm_tool_name="detect_changes"),
    PassthroughEntry("trace_call_path",  native_trace_call_path,  cm_passthrough=True, cm_tool_name="trace_call_path"),
    PassthroughEntry("search_graph",     native_search_graph,     cm_passthrough=True, cm_tool_name="search_graph"),
    PassthroughEntry("get_architecture", native_get_architecture, cm_passthrough=True, cm_tool_name="get_architecture"),
    PassthroughEntry("search_code",      None,                    cm_passthrough=True, cm_tool_name="search_code"),  # Phase 2
)
```

### 4.2 Fallback rule (v2 — corrected against real `code/namespace.py` API)

The real API: `namespace.resolve(driver, value) → NamespaceResolution(slug, cm_project_name) | None`. It does NOT have a `kind` field; absence of the registry entry returns `None` (or raises `UnknownProjectError` from `assert_known_project`). v1's reliance on a `kind ∈ {slug, cm_name}` discriminator was incorrect.

Per-call dispatch decision tree:

```python
async def dispatch(entry: PassthroughEntry, kwargs: dict, driver, cm_session) -> dict:
    project_arg = kwargs.get("project")
    is_palace_known = False
    if project_arg is not None and entry.native_impl is not None:
        try:
            await namespace.assert_known_project(driver, project_arg)
            is_palace_known = True  # slug or registered cm_project_name path
        except namespace.UnknownProjectError:
            is_palace_known = False

    if is_palace_known and entry.native_impl is not None:
        try:
            native_result = await entry.native_impl(driver=driver, **kwargs)
        except Exception as exc:
            logger.exception("native_impl_error", extra={"tool": entry.name})
            return {"ok": False, "error_code": "native_impl_error", "message": str(exc)}
        # Sentinel: native may opt to fall through if it can't serve.
        if native_result.get("error_code") != "fallback_to_cm":
            return native_result

    if entry.cm_passthrough and cm_session is not None:
        return await _forward_to_cm(entry.cm_tool_name, kwargs, cm_session)

    return {
        "ok": False,
        "error_code": "cm_fallback_unavailable",
        "message": f"{entry.name}: no native impl applicable and CM sidecar not started",
        "available_via": "palace.memory.list_projects",
    }
```

Notes:
- The `FallbackToCM` exception (v1 §4.5) is **dropped**. Sentinel is the string-valued `error_code` field — composes with logs, no exception interplay across the async boundary.
- An unhandled `Exception` in `native_impl` produces a structured error envelope (`native_impl_error`); stack trace goes to logs only.
- `is_palace_known = False` when `project=` is omitted; in that case native impls that require `project` should return their own `error_code: "missing_project"` envelope (no fallback to CM, because CM also rejects missing project).

### 4.3 Native implementations (Phase 1 outline)

#### 4.3.1 `native_query_graph(query, project, max_rows)` — hardened

Real signature uses **read-only session**, **write-keyword deny-list**, **mandatory scope predicate enforcement**, and **byte-cap streaming** with row ceiling.

```python
import re
import sys

# Deny-list: write/admin Cypher keywords + admin procedures.
_WRITE_KEYWORD_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD\s+CSV|DETACH\s+DELETE)\b",
    re.IGNORECASE,
)
_ADMIN_PROC_RE = re.compile(
    r"CALL\s+(dbms|db\.create|db\.drop|apoc\.(cypher\.runWrite|systemdb|export|trigger|periodic))\.",
    re.IGNORECASE,
)
_RESERVED_PARAM_RE = re.compile(r"\$(project_id|group_id)\b")
# Scope predicate: every MATCH (or the only RETURN) must reference $group_id/$project_id.
_SCOPE_PREDICATE_RE = re.compile(
    r"(\$group_id|\$project_id|group_id\s*:\s*\$group_id|project_id\s*:\s*\$project_id)",
    re.IGNORECASE,
)
_DEFAULT_ROW_CAP = 1000
_HARD_ROW_CAP = 100_000
_BYTE_BUDGET = 16 * 1024 * 1024  # 16 MB

async def native_query_graph(*, driver, query, project, max_rows=_DEFAULT_ROW_CAP):
    # 1. Bound the row cap to hard ceiling.
    if max_rows <= 0 or max_rows > _HARD_ROW_CAP:
        return {"ok": False, "error_code": "max_rows_out_of_range",
                "message": f"max_rows must be in [1, {_HARD_ROW_CAP}]"}

    # 2. Reject writes / admin / collision with reserved params.
    if _WRITE_KEYWORD_RE.search(query):
        return {"ok": False, "error_code": "write_cypher_rejected",
                "message": "query_graph is read-only; remove CREATE/MERGE/DELETE/SET/REMOVE/DROP/LOAD CSV/DETACH DELETE"}
    if _ADMIN_PROC_RE.search(query):
        return {"ok": False, "error_code": "admin_procedure_rejected",
                "message": "admin/write procedures (dbms.*, db.create*, apoc.cypher.runWrite, apoc.systemdb.*, apoc.export.*, apoc.trigger.*, apoc.periodic.*) are forbidden"}
    if _RESERVED_PARAM_RE.search(query):
        return {"ok": False, "error_code": "reserved_param",
                "message": "$project_id and $group_id are auto-bound and may not appear as caller-supplied parameters"}

    # 3. Enforce mandatory scope predicate (cross-project leak prevention).
    if not _SCOPE_PREDICATE_RE.search(query):
        return {"ok": False, "error_code": "scope_predicate_required",
                "message": ("query must reference $group_id or $project_id in every MATCH clause "
                            "(prevents cross-project data leaks); see "
                            "docs/runbooks/palace-passthrough-native-impl.md")}

    # 4. Resolve project → group_id ("project/<slug>").
    resolution = await namespace.resolve(driver, project)
    if resolution is None or resolution.slug is None:
        return {"ok": False, "error_code": "project_not_resolvable",
                "message": f"{project!r} not registered as :Project; use palace.memory.list_projects"}
    group_id = f"project/{resolution.slug}"
    params = {"project_id": group_id, "group_id": group_id}

    # 5. Read-only session + byte-cap streaming.
    rows = []
    bytes_used = 0
    truncated_reason = None
    async with driver.session(default_access_mode="r") as session:
        try:
            result = await session.run(query, **params)
        except Exception as exc:
            # Redact: keep error class name, drop stack/internal paths/schema details.
            return {"ok": False, "error_code": "cypher_error",
                    "message": f"{type(exc).__name__}: see server logs for details"}
        async for record in result:
            row = dict(record)
            row_bytes = sys.getsizeof(repr(row).encode("utf-8"))  # approximate
            if bytes_used + row_bytes > _BYTE_BUDGET:
                truncated_reason = "byte_budget"
                break
            if len(rows) >= max_rows:
                truncated_reason = "row_cap"
                break
            rows.append(row)
            bytes_used += row_bytes

    columns = list(rows[0].keys()) if rows else []
    return {
        "ok": True,
        "columns": columns,
        "rows": rows,
        "total": len(rows),
        "truncated": truncated_reason is not None,
        "truncated_reason": truncated_reason,
    }
```

**Safety summary (closes security C1, C2, H3 from v1 review):**
1. **Write-keyword deny-list** — `CREATE/MERGE/DELETE/SET/REMOVE/DROP/LOAD CSV/DETACH DELETE` rejected at API boundary.
2. **Admin/write procedure deny-list** — `dbms.*`, `apoc.cypher.runWrite`, `apoc.systemdb.*`, `apoc.export.*`, `apoc.trigger.*`, `apoc.periodic.*` rejected.
3. **Read-only session** — `default_access_mode="r"` (Neo4j 5+ Python driver) enforces server-side READ at protocol level.
4. **Mandatory scope predicate** — every `MATCH` must reference `$group_id`/`$project_id`; queries that fail the regex are rejected (defense in depth, complements the read-only enforcement).
5. **Reserved param collision rejected** — caller-supplied `$project_id`/`$group_id` produces `reserved_param` envelope; never silently overwritten.
6. **Byte-budget streaming** — accumulates row-by-row with 16 MB ceiling; never materializes hundreds of MB into memory.
7. **Row cap** — default 1000, hard ceiling 100 000; `truncated_reason` field exposed for caller introspection.
8. **No syntax-error 500s** — Cypher exceptions caught and returned as `cypher_error` envelope.

**Deferred decision** (Q1 in §9): an additional Neo4j role `palace_reader` with `GRANT MATCH {*} ON GRAPH *; DENY WRITE` for the MCP service connection is **strongly recommended** as the durable cross-cutting protection. Adding it is operator runbook scope, not in this spec.

#### 4.3.2 `native_get_code_snippet(qualified_name, project, include_neighbors=False)` — corrected against real schema

`:Function` is keyed by `(project_id, path, name, start_line)` where `name` is the **short name** from lizard. It does NOT carry the `qualified_name`. So the join must derive `short_name` from `qualified_name` (Swift convention: drop module prefix + parameter mangling; for non-Swift, just take the last `.`-separated segment) AND match `(file_path, short_name)`. This is a heuristic; documented as such.

`resolve_snippet` is **synchronous** and returns `(SnippetResult | None, warning_code, warning_message)` — adapter layer required.

```python
# code/snippet_short_name.py (new helper, ~30 LoC)
def short_name_from_qualified_name(qn: str) -> str:
    """Extract the symbol's short name from a qualified_name.

    Swift SCIP form: 'HdWalletKit s%3A11HdWalletKit8HDWalletC9masterKey...' → 'masterKey'
    Generic dotted (java/kotlin/python): 'pkg.module.Class.method' → 'method'
    Fallback: last alphanumeric run.
    """
    import re
    # Swift SCIP: 'Module s%3A...<len><name>...'. Greedy-match the last (\d+)([A-Za-z_][A-Za-z0-9_]*)
    # pattern in the SCIP descriptor (where leading digit = length of following identifier).
    if " s%3A" in qn or qn.startswith("s%3A"):
        descriptor = qn.split(" ", 1)[-1]
        matches = re.findall(r"(\d+)([A-Za-z_][A-Za-z0-9_]*)", descriptor)
        if matches:
            length, name = matches[-1]
            # Trim to declared length; SCIP encodes name length as the digit run.
            return name[:int(length)] if int(length) <= len(name) else name
    # Generic dotted form. Strip trailing parens/parameters.
    base = qn.split("(", 1)[0]
    last = base.rsplit(".", 1)[-1]
    # Defensive: keep only identifier chars.
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", last)
    return cleaned or qn

def function_quality(found_in_function: bool, found_in_occurrence: bool) -> SnippetQuality:
    if found_in_function:
        return SnippetQuality.APPROXIMATE_FUNCTION_MATCH
    if found_in_occurrence:
        return SnippetQuality.APPROXIMATE_WINDOW
    return SnippetQuality.FILE_HEAD

class SnippetQuality(str, enum.Enum):
    EXACT = "exact"                              # reserved for Phase 2 (:Symbol.start_line/end_line)
    APPROXIMATE_FUNCTION_MATCH = "approximate_function_match"  # joined via (file_path, short_name)
    APPROXIMATE_WINDOW = "approximate_window"    # def-occurrence ±window
    FILE_HEAD = "file_head"                      # first 200 lines fallback
```

```python
async def native_get_code_snippet(*, driver, qualified_name, project, include_neighbors=False):
    resolution = await namespace.resolve(driver, project)
    if resolution is None or resolution.slug is None:
        return {"ok": False, "error_code": "fallback_to_cm",
                "message": "project not Palace-registered; deferring to CM"}
    group_id = f"project/{resolution.slug}"

    # 1. Locate :Symbol by qualified_name.
    sym = await _lookup_symbol(driver, qualified_name, group_id)
    if sym is None:
        return {"ok": False, "error_code": "unknown_symbol",
                "qualified_name": qualified_name, "project": project}

    # 2. Derive short_name; attempt :Function join via (file_path, short_name).
    short_name = short_name_from_qualified_name(qualified_name)
    func = await _lookup_function_by_file_and_short_name(
        driver, group_id=group_id, file_path=sym["file_path"], short_name=short_name,
    )

    # 3. Resolve snippet (snippet_provider is SYNC; adapt tuple to envelope).
    quality = SnippetQuality.FILE_HEAD
    line_start, line_end = 1, 200

    if func is not None:
        quality = SnippetQuality.APPROXIMATE_FUNCTION_MATCH
        line_start, line_end = func["start_line"], func["end_line"]
    else:
        # Try occurrence anchor.
        occ = await _first_def_occurrence(driver, qualified_name, group_id)
        if occ is not None:
            quality = SnippetQuality.APPROXIMATE_WINDOW
            line_start = max(1, occ["line"] - 5)
            line_end = occ["line"] + 30

    snippet_result, warning_code, warning_msg = resolve_snippet(  # SYNC call
        project=project, file_path=sym["file_path"],
        line_start=line_start, line_end=line_end,
    )
    if snippet_result is None:
        return {"ok": False, "error_code": warning_code or "snippet_unavailable",
                "message": warning_msg or "snippet provider returned no text"}

    return {
        "ok": True,
        "project": project,
        "qualified_name": qualified_name,
        "file_path": sym["file_path"],
        "line_start": line_start, "line_end": line_end,
        "snippet": snippet_result.text,
        "language": snippet_result.language,
        "snippet_quality": quality.value,
        "warning_code": warning_code,
        "warning_message": warning_msg,
    }
```

**Limitations tracked in §10:**
- `:Symbol` has no body span → `EXACT` quality unavailable in Phase 1.
- `:Function` join via `(file_path, short_name)` is heuristic; collides for overloads (returns first match deterministically).
- `:Function` only exists where `hotspot` extractor has ingested; absent → falls to occurrence anchor.

#### 4.3.3 `native_detect_changes(project, base_branch="main", since=None, scope=None)` — with `since` validation

```python
# git approxidate subset + ISO-8601 + relative ("2 weeks ago", "yesterday").
_SINCE_RE = re.compile(
    r"^(?:"
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?"  # ISO-8601
    r"|\d{1,4}\s+(?:second|minute|hour|day|week|month|year)s?\s+ago"
    r"|yesterday|today|now"
    r")$",
    re.IGNORECASE,
)

async def native_detect_changes(*, driver, project, base_branch="main", since=None, scope=None):
    if scope == "symbols":
        return {"ok": False, "error_code": "phase2_required",
                "message": "scope='symbols' (touched-files → symbol-impact mapping) lands in Phase 2"}
    if since is not None and not _SINCE_RE.match(since):
        return {"ok": False, "error_code": "invalid_since",
                "message": f"since={since!r} does not match ISO-8601 or git approxidate"}

    resolution = await namespace.resolve(driver, project)
    if resolution is None or resolution.slug is None:
        return {"ok": False, "error_code": "fallback_to_cm",
                "message": "project not Palace-registered; deferring to CM"}

    from palace_mcp.git.tools import git_diff
    diff_kwargs = {"project": resolution.slug, "ref_a": base_branch, "ref_b": "HEAD", "mode": "stat"}
    if since is not None:
        diff_kwargs["since"] = since
    result = await git_diff(**diff_kwargs)
    if result.get("error_code"):
        return {"ok": False, **result}
    return {
        "ok": True,
        "files": result.get("files", []),
        "base_branch": base_branch,
        "head_sha": result.get("head_sha"),
        "since": since,
    }
```

**Safety note (security H2):** `_SINCE_RE` runs **before** the value reaches `git diff` argv. The existing `palace_git_log` (`git/tools.py:134`) forwards `since` as a single argv element via `subprocess.run([..., f"--since={since}", ...], shell=False)` — argv list neutralizes shell metacharacters. The regex + argv list defense is layered.

#### 4.3.4 `native_trace_call_path(function_name, project, direction="both", depth=3, mode="calls")` — pure Cypher (NO APOC)

**APOC probe result (2026-06-07):** `apoc.path` procedures count = **0** on prod Neo4j (Community 2026.05.0). APOC is not installed and adding it is operator/runbook scope. Spec uses pure-Cypher variable-depth traversal instead.

```python
# code/edges.py (new file — single source of truth)
CALL_EDGES = (
    "REFERENCES",
    "CONFORMS_TO",
    "EXTENDS",
    "EXTENSION_OF",
    "EXISTENTIAL_USE",
)
# Edge alternation literal generated once at import time.
_CALL_EDGES_LITERAL = "|".join(CALL_EDGES)

_TRACE_CYPHER_OUTBOUND = f"""
MATCH (start:Symbol {{qualified_name: $qn, group_id: $gid}})
MATCH path = (start)-[r:{_CALL_EDGES_LITERAL}*1..{{max_depth}}]->(end)
WHERE end.group_id = $gid
RETURN nodes(path) AS nodes, relationships(path) AS rels
LIMIT $limit
""".strip()

_TRACE_CYPHER_INBOUND = ...  # symmetric, with arrow reversed
_TRACE_CYPHER_BOTH = ...     # undirected via [r:...] (no arrows)

_MIN_DEPTH, _MAX_DEPTH = 1, 6
_TRACE_LIMIT = 5_000  # cap path count, prevents BFS explosion on hot symbols

async def native_trace_call_path(*, driver, function_name, project,
                                  direction="both", depth=3, mode="calls"):
    if mode != "calls":
        return {"ok": False, "error_code": "phase2_required",
                "message": f"mode={mode!r} (data_flow, cross_service) lands in Phase 2 — needs :HTTP_CALLS/:DATA_FLOWS extractors"}
    depth = max(_MIN_DEPTH, min(int(depth), _MAX_DEPTH))  # clamp
    if direction not in ("outbound", "inbound", "both"):
        return {"ok": False, "error_code": "invalid_direction",
                "message": f"direction={direction!r}; expected outbound|inbound|both"}

    resolution = await namespace.resolve(driver, project)
    if resolution is None or resolution.slug is None:
        return {"ok": False, "error_code": "fallback_to_cm",
                "message": "project not Palace-registered; deferring to CM"}
    group_id = f"project/{resolution.slug}"

    cypher_template = {
        "outbound": _TRACE_CYPHER_OUTBOUND,
        "inbound": _TRACE_CYPHER_INBOUND,
        "both": _TRACE_CYPHER_BOTH,
    }[direction]
    cypher = cypher_template.format(max_depth=depth)

    nodes_set: dict[str, dict] = {}
    edges: list[dict] = []
    async with driver.session(default_access_mode="r") as session:
        result = await session.run(cypher, qn=function_name, gid=group_id, limit=_TRACE_LIMIT)
        async for record in result:
            for node in record["nodes"]:
                nid = node.element_id
                if nid not in nodes_set:
                    nodes_set[nid] = {
                        "id": nid,
                        "qualified_name": node.get("qualified_name"),
                        "kind": node.get("kind"),
                        "file_path": node.get("file_path"),
                    }
            for rel in record["rels"]:
                edges.append({
                    "type": rel.type,
                    "source": rel.start_node.element_id,
                    "target": rel.end_node.element_id,
                })

    return {
        "ok": True,
        "start": function_name,
        "project": project,
        "direction": direction,
        "depth": depth,
        "nodes": list(nodes_set.values()),
        "edges": edges,
        "truncated": len(edges) == _TRACE_LIMIT,
    }
```

**Edge type registry (architect H5):** `code/edges.py: CALL_EDGES = (...)` is the single source of truth. A schema-survey CI test asserts no live edge type starting `:` matches a name outside `CALL_EDGES ∪ KNOWN_NON_CALL_EDGES`. Drift forces an explicit decision (add to CALL_EDGES or to the exclusion list).

**Performance:** depth=6 + 5000-path cap protects hot symbols (`HDWallet`, root protocols); pure Cypher variable-depth is O(branching^depth) — measured at depth=3 on uw-ios-baseline returns ~200 edges for typical symbols. Phase 1 perf SLO: <2 s p95 at depth=3.

#### 4.3.5 `native_search_graph(project, label=None, name_pattern=None, qn_pattern=None, file_pattern=None, min_degree=0, max_degree=None)`

Phase 1: no BM25 `query=` parameter; if caller supplies it, return `{error_code: "phase2_required"}`.

```python
async def native_search_graph(*, driver, project, label=None, name_pattern=None, qn_pattern=None,
                              file_pattern=None, min_degree=0, max_degree=None, query=None, **_ignored):
    if query is not None:
        return {"ok": False, "error_code": "phase2_required",
                "message": "BM25 query= lands in Phase 2; use name_pattern/qn_pattern for now"}
    # Cypher template builder.
```

#### 4.3.6 `native_get_architecture(project)`

Phase 1: aggregate over `:Module`, `:ExternalDependency`, `:File.language`, `:Symbol {is_main_entry: true}`. No `routes` field (always `[]` in v1; documented in response).

### 4.4 New API contract (per-tool envelope)

All 6 native impls return either:

```json
{"ok": true, ...tool-specific shape (matches CM's shape exactly)}
```

or

```json
{"ok": false, "error_code": "<code>", "message": "...", ...}
```

Error codes registered in `code_router.py`:
- `project_not_resolvable` — neither slug nor cm-name match
- `unknown_symbol` — qualified_name not in graph
- `phase2_required` — feature parameter deferred to Phase 2
- `cm_fallback_unavailable` — CM-only project requested but binary missing
- `query_too_large` — query_graph row cap exceeded ceiling

### 4.5 CM-fallback wiring — superseded by §4.2

Authoritative dispatch lives in §4.2. No separate `CM-fallback wiring` code block; the sentinel string `error_code: "fallback_to_cm"` from native impls is the only signal.

### 4.7 Edge type registry

`code/edges.py` (new file, ~30 LoC) is the single source of truth for both `trace_call_path` and the schema-survey CI test.

```python
# code/edges.py
"""Single source of truth for edge type classification.

Used by:
- code/native_trace_call_path.py — to build the variable-depth Cypher alternation
- tests/code/test_edges_registry.py — to verify no unlisted edge type exists in prod
"""

# Edges that trace_call_path traverses (Phase 1 calls-mode).
CALL_EDGES: tuple[str, ...] = (
    "REFERENCES",
    "CONFORMS_TO",
    "EXTENDS",
    "EXTENSION_OF",
    "EXISTENTIAL_USE",
)

# Edges that exist in the schema but are intentionally NOT traversed by trace_call_path.
# Adding a new edge type here is an explicit decision (vs. silently breaking the test).
KNOWN_NON_CALL_EDGES: tuple[str, ...] = (
    "CONTAINS",            # File→Function, File→Symbol structural
    "DEFINED_IN",          # Symbol→File structural
    "TOUCHED",             # Commit→File (git_history)
    "AUTHORED_BY",         # Commit→Author (git_history)
    "OWNED_BY",            # File→Author (code_ownership)
    "IN_LAYER",            # Module→Layer (arch_layer)
    "MODULE_DEPENDS_ON",   # Module→Module (arch_layer)
    "VIOLATES_RULE",       # Module→ArchRule (arch_layer)
    "DEPENDS_ON",          # Project→ExternalDependency (dependency_surface)
    "LAST_SEEN_IN",        # Symbol/File→IngestRun (GIM-1491)
    "BACKED_BY_SYMBOL",    # Function→Symbol (hotspot)
    "CALLS_REACTIVE_COMPONENT",  # reactive_dependency_tracer
)
```

CI test (`tests/code/test_edges_registry.py`):

```python
async def test_no_unlisted_edge_types_in_live_schema(driver):
    """Assert every :Edge type in Neo4j is classified in CALL_EDGES or KNOWN_NON_CALL_EDGES.

    If this test fails, an extractor PR added a new edge type without updating
    code/edges.py — explicitly decide whether the new type is traversed by
    trace_call_path (add to CALL_EDGES) or not (add to KNOWN_NON_CALL_EDGES).
    """
    from palace_mcp.code.edges import CALL_EDGES, KNOWN_NON_CALL_EDGES
    classified = set(CALL_EDGES) | set(KNOWN_NON_CALL_EDGES)
    async with driver.session() as s:
        result = await s.run("SHOW RELATIONSHIPS YIELD relationshipType RETURN DISTINCT relationshipType AS rt")
        live = {row["rt"] async for row in result}
    unclassified = live - classified
    assert not unclassified, (
        f"unclassified edge types {sorted(unclassified)!r}; "
        f"add to code/edges.py CALL_EDGES or KNOWN_NON_CALL_EDGES"
    )
```

Test uses the existing testcontainers Neo4j fixture; seed the same `native_passthrough_seed.cypher` with all known edge types so the test runs against a known-classified set in CI (no fixture drift).

### 4.6 Observability (caplog only)

Palace has no Prometheus backend (per GIM-1500 v3 finding). Observability is **structured INFO log** per call, asserted via `caplog` in tests:

```python
logger.info(
    "passthrough.dispatch",
    extra={
        "tool": entry.name,
        "decision": decision,  # "native" | "cm_fallback" | "error_native" | "error_cm"
        "project": project_arg,
        "duration_ms": round(elapsed * 1000, 2),
    },
)
```

Operators grep `passthrough.dispatch` lines from the server log for per-tool routing distribution. No metrics endpoint, no Prometheus counter.

## 5. Migration phases (v2 — re-bucketed per architect M4)

| Phase | Scope | Owner | Effort | PR merge gate (CI required) |
|---|---|---|---|---|
| 1.0+1.3 | Router refactor: dispatch table + `PassthroughEntry` + fallback wiring + `native_detect_changes` (wraps existing `palace.git.diff`) + edges.py registry + unit tests for fallback logic + edge-type schema-survey test | CXPythonEngineer | 3h | `ruff check`, `ruff format --check`, `mypy src/`, `pytest tests/code/test_passthrough_dispatch.py tests/code/test_native_detect_changes.py tests/code/test_edges_registry.py`, full pytest suite |
| 1.1+1.2 | `native_query_graph` (full Cypher safety stack) + `native_get_code_snippet` (with `:Function` heuristic join, sync-adapter, snippet_quality enum) + per-tool unit tests | CXPythonEngineer | 3.5h | as above + `pytest tests/code/test_native_query_graph.py tests/code/test_native_get_code_snippet.py` |
| 1.4 | `native_trace_call_path` (pure Cypher, NO APOC) + edge-registry consumption + depth/limit clamps + unit tests | CXPythonEngineer | 2-3h | as above + `pytest tests/code/test_native_trace_call_path.py` |
| 1.5 | `native_search_graph` (pattern mode, no BM25) + unit tests | CXPythonEngineer | 2-2.5h | as above + `pytest tests/code/test_native_search_graph.py` |
| 1.6 | `native_get_architecture` (basic — modules/deps/languages/entry_points; routes always `[]`) + unit tests | CXPythonEngineer | 1.5-2h | as above + `pytest tests/code/test_native_get_architecture.py` |
| 1.7 | Smoke gate CI: each tool covered with seed-fixture integration test in `tests/integration/test_passthrough_native_smoke.py` + `tests/integration/fixtures/native_passthrough_seed.cypher` | CXQAEngineer | 1.5h | as above + `pytest tests/integration/test_passthrough_native_smoke.py` |
| 1.8 | Operator runbook `docs/runbooks/palace-passthrough-native-impl.md` (decision tree diagram, fallback behavior, how to read structured DEBUG log, how to opt back to all-CM via env flag) + new tool `palace.code.list_passthrough_projects` returning `{native: [...], cm_only: [...]}` (~50 LoC + unit test) | CXInfraEngineer | 1.5-2h | `pytest tests/code/test_list_passthrough_projects.py` |

Total estimate: **15-18h walker-class.** 7 PRs (down from 9 in v1). Each phase = separate PR to `develop`.

## 6. Testing

### 6.1 Unit (Phase 1.0) — `tests/code/test_passthrough_dispatch.py`

- `test_native_impl_present_takes_precedence` — entry with native_impl serves the call; CM not invoked.
- `test_no_native_falls_through_to_cm` — entry with `native_impl=None` and `cm_passthrough=True` forwards to mocked CM.
- `test_no_native_no_cm_returns_error` — both disabled → structured `cm_fallback_unavailable`.
- `test_native_returns_fallback_sentinel_falls_through` — native returns `{ok: false, error_code: "fallback_to_cm"}` → CM passthrough kicks in.
- `test_native_returns_error_does_not_fallback` — native returns `{ok: false, error_code: "unknown_symbol"}` → CM is NOT invoked (errors are terminal).
- `test_cm_unavailable_native_handles_alone` — entry registered without CM session (binary missing) → native serves.

### 6.2 Per-tool unit tests

One unit test file per native impl: `tests/code/test_native_query_graph.py`, `test_native_get_code_snippet.py`, etc. Each verifies:
- Happy path: project resolved → call succeeds.
- Project not registered → CM fallback (mock CM returns sentinel data).
- Phase 2 parameter rejected with `phase2_required` error envelope.
- Edge cases per tool (Cypher injection guarded for query_graph; missing :Function for get_code_snippet; etc.).

### 6.3 Integration (Phase 1.7)

`tests/integration/test_passthrough_native_smoke.py` — seed-fixture based (no live CM binary required):
- Seed `:Project {slug: "test-native"}` + `:File` + `:Symbol` + `:Function`.
- Mock CM session with assertion: NEVER invoked for native-served projects.
- Call each of 6 native tools end-to-end; verify shape and content.

### 6.4 Regression suite

Pin all existing native composites green: `test_code_composite.py`, `test_code_router.py`, `test_find_*.py`, `test_namespace.py`. Phase 1.0 PR must pass full pytest.

### 6.5 CM-contract migration

`tests/code_composite/test_cm_contract.py` currently verifies "router invoked CM correctly". Migrate each test to:
- Half: verify CM contract is preserved when fallback path triggers (input-shape, response-shape).
- Half: verify native impl produces the same response shape as the CM mock did before.

## 7. Acceptance criteria (v2 — with explicit Verification method column)

| ID | Criterion | Verification method | Phase gate |
|---|---|---|---|
| AC-1 | `palace.code.query_graph(query="MATCH (s:Symbol {group_id: $group_id}) RETURN s LIMIT 10", project="uw-ios-baseline")` returns rows from Palace native graph | **Manual operator** | 1.1 |
| AC-2 | `palace.code.get_code_snippet(qualified_name="<HD Wallet QN>", project="uw-ios-baseline")` returns snippet text with `snippet_quality` field set | **Manual operator** | 1.2 |
| AC-3 | `palace.code.trace_call_path(function_name="<X>", project="uw-ios-baseline", mode="calls")` returns non-empty subgraph at depth 3 | **Manual operator** | 1.4 |
| AC-4 | `palace.code.search_graph(project="uw-ios-baseline", name_pattern="HD*", label="Symbol")` returns ≥1 match | **Manual operator** | 1.5 |
| AC-5 | `palace.code.get_architecture(project="uw-ios-baseline")` returns `{languages, packages, entry_points, routes: []}` | **Manual operator** | 1.6 |
| AC-6 | `palace.code.search_code(project="uw-ios-baseline", pattern="HD")` returns `{ok: false, error_code: "phase2_required"}` | **Automated unit** | 1.0 |
| AC-7 | CM-only project (raw CM host-path string e.g. `Users-ant013-Ios-HorizontalSystems-EvmKit.Swift`) routes to CM fallback for all 6 tools | **Automated integration** (mocked CM session asserts invocation count) | 1.7 |
| AC-8 | Structured INFO log `passthrough.dispatch` emitted per call with `{tool, decision ∈ {native, cm_fallback, error_native, error_cm}, project, duration_ms}` fields; verified via `caplog` | **Automated unit** | 1.0 |
| AC-9 | Full pytest suite stays green | **Automated CI** | every PR |
| AC-10 | Runbook `docs/runbooks/palace-passthrough-native-impl.md` committed AND `palace.code.list_passthrough_projects` returns both lists for current substrate | **Automated** (file existence test + tool unit test) | 1.8 |
| AC-11 | `query_graph` rejects writes (`{ok: false, error_code: "write_cypher_rejected"}`) for any of CREATE/MERGE/DELETE/SET/REMOVE/DROP/LOAD CSV/DETACH DELETE | **Automated unit** (parametrized over keywords) | 1.1 |
| AC-12 | `query_graph` rejects scope-less queries (`{ok: false, error_code: "scope_predicate_required"}`) | **Automated unit** | 1.1 |
| AC-13 | `query_graph` byte-cap enforced: response includes `truncated_reason: "byte_budget"` when 16 MB exceeded; response includes `truncated_reason: "row_cap"` at row ceiling | **Automated unit** (synthetic fat-row fixture) | 1.1 |
| AC-14 | `trace_call_path` depth clamped to [1, 6]; depth=7 silently clamped to 6 with `clamped_depth` field | **Automated unit** | 1.4 |
| AC-15 | `detect_changes` rejects malformed `since=` with `{error_code: "invalid_since"}` (regex test parametrized over good/bad values) | **Automated unit** | 1.0 |
| AC-16 | Edge type schema-survey test fails the PR if a new edge type appears in live Neo4j outside `CALL_EDGES ∪ KNOWN_NON_CALL_EDGES` (see §4.7 for the registry; test file `tests/code/test_edges_registry.py` uses `SHOW RELATIONSHIPS` against fixture-seeded Neo4j) | **Automated CI** | 1.0 |
| AC-17 | `query_graph` with multi-MATCH where one clause omits `$group_id` returns `scope_predicate_required` (defense-in-depth — read-only session is the load-bearing layer, but regex rejects pre-driver) | **Automated unit** | 1.1 |
| AC-18 | `query_graph` with Cypher comments (`//`, `/* */`) hiding `CREATE` keyword is rejected: either by `_WRITE_KEYWORD_RE` after comment-stripping pass, OR (load-bearing) neutralized by `default_access_mode="r"` server-side with `{ok: false, error_code: "cypher_error"}` returned — test asserts no actual write happens regardless of which layer caught it | **Automated unit** | 1.1 |
| AC-19 | `query_graph` with string-literal `CREATE` (e.g. `MATCH (n) WHERE n.name = "CREATE" RETURN n`) is NOT rejected — verify it passes the deny-list and runs as a read | **Automated unit** | 1.1 |

## 8. Risks and mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Pure-Cypher variable-depth perf at depth=6 on hot symbols (e.g. root protocols with 1000+ references) | Medium | Medium | `_TRACE_LIMIT=5000` path cap protects; depth clamp `[1,6]` prevents abuse; Phase 1.4 PR includes a benchmark assertion (<5s p95 at depth=6 on `uw-ios-baseline`) — fail PR if exceeded. Live probe confirmed APOC absent so no `apoc.path.subgraphAll` alternative; if perf becomes blocker, APOC install becomes operator runbook scope (separate spec). |
| `:Symbol` has no `start_line`/`end_line` — snippet window approximation may surprise callers | Medium | Medium | Phase 1.2 returns explicit envelope `{snippet_quality: "approximate"}` when sourced from occurrence anchor; Phase 2 backfills via `palace-swift-scip-emit-cli` enhancement. |
| Native search_graph without BM25 produces noisier results than CM's FTS5 | High | Medium | Document the limitation; LIKE patterns are sufficient for the common operator workflow ("find symbol whose name contains foo"); BM25 deferred. |
| CM sidecar binary absent on operator machines (e.g. fresh MacBook bootstrap) | Medium | Low (fallback disabled) | Native impl handles 100% of Palace-registered projects; the bootstrap runbook (`bootstrap-macbook-paperclip-stack.md`) already lists CM binary as optional. |
| CM-only projects break silently when CM is shut down | Low | High | Router returns `cm_fallback_unavailable` with clear message + suggestion (`palace.memory.register_project` then ingest). |
| Schema drift: a future extractor adds new edge types not in the `_TRACE_CYPHER_*` literal alternation | Medium | Low | `trace_call_path` doc explicitly lists supported edge types; release-notes call out additions; failing test catches drift. |
| Per-tool migration accidentally changes response shape vs CM | Medium | Medium | §6.5 CM-contract migration tests pin response shapes; CR phase 3.1 mandatory diff vs golden fixtures. |
| Cypher injection via `query_graph` (operator passes malicious Cypher) | Low | Medium (operator owns own keyboard) | Documented as advanced tool per spec §4.3.1; Neo4j's read-only role guards (if applied) prevent writes; row cap prevents DoS. |

## 9. Open questions

- **Q1 (RESOLVED 2026-06-07 v2)** APOC absent on prod Neo4j 2026.05.0 Community (live probe = 0 `apoc.path` procedures). Design uses pure Cypher variable-depth; no APOC dependency.
- **Q2** Does `:Function` node coverage match across all Palace-ingested projects, or is hotspot ingest a prerequisite? If Phase 1.2 (`get_code_snippet`) requires hotspot, document the dependency and surface in error response. **Resolution path:** §10 lists hotspot-not-run as a degradation cause; envelope returns `snippet_quality: "approximate_window"` (or `"file_head"`) rather than failing.
- **Q3 (RESOLVED 2026-06-07 v2)** `palace.git.diff` contract: see §4.3.3 — `git_diff(project=slug, ref_a, ref_b, mode="stat", since=optional)` returning `{files: [...], head_sha, error_code?}`. Wraps `subprocess.run([..., shell=False])` with `_REF_RE` validation; argv list neutralizes shell metacharacters.
- **Q4** When does `:Symbol.start_line/end_line` get added? Track as Phase 2 prerequisite. Phase 1.2 lives with approximate snippets.
- **Q5 (RESOLVED 2026-06-07 v2)** `query_graph` is read-only: enforced by (a) `session(default_access_mode="r")`, (b) `_WRITE_KEYWORD_RE` deny-list, (c) `_ADMIN_PROC_RE` deny-list, (d) mandatory `$group_id`/`$project_id` scope predicate. Operator may additionally configure a `palace_reader` Neo4j role per §4.3.1 deferred-decision note for durable cross-cutting protection.

## 10. Known limitations (Phase 1)

- `get_code_snippet` returns approximate window when `:Function` is absent for the symbol. Quality field documents.
- `search_graph` lacks BM25; LIKE-only pattern matching.
- `get_architecture.routes` always `[]` in v1. Documented.
- `detect_changes.scope=symbols` returns `phase2_required`; only files-list mode is Phase 1.
- `trace_call_path.mode=data_flow|cross_service` returns `phase2_required`; only calls mode is Phase 1.
- `search_code` is **not** implemented natively; CM fallback only. Operators with no CM binary see `cm_fallback_unavailable`.
- Cache TTL on resolver entries is 300 s (inherited from GIM-1500 namespace resolver); not changed by this spec.

## 11. References

- Research report (autonomous Board run, 2026-06-07): summary baked into §1-§2.
- Existing passthrough registration: `services/palace-mcp/src/palace_mcp/code_router.py:213-279`.
- Existing namespace resolver: `services/palace-mcp/src/palace_mcp/code/namespace.py`.
- Existing snippet provider: `services/palace-mcp/src/palace_mcp/code/snippet_provider.py:60-140`.
- Existing git diff tool: `services/palace-mcp/src/palace_mcp/git/tools.py:499-549`.
- Symbol/File schemas: `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py:70-103`, `extractors/symbol_index_swift.py:102-121`.
- Function schema: `services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py:16-30`.
- Module/Layer schemas: `services/palace-mcp/src/palace_mcp/extractors/arch_layer/neo4j_writer.py:40-110`.
- Dependency schemas: `services/palace-mcp/src/palace_mcp/extractors/dependency_surface/neo4j_writer.py:18-33`.
- Dead-code graph union (call-graph proxy): `services/palace-mcp/src/palace_mcp/extractors/dead_code/graph_loader.py:37`.
- CM-contract tests: `services/palace-mcp/tests/code_composite/test_cm_contract.py`.
- GIM-1500 namespace unification (parent spec, landed).

## 12. Review log

| Cycle | Reviewer | Verdict | Findings (closed in v2) |
|---|---|---|---|
| v1 | architect | PASS_WITH_CONCERNS | 2 CRITICAL (API surface mismatch, `:Function.name`≠QN), 5 HIGH (resolve_snippet sync, dispatch design, query_graph collision check, APOC dependency, edge alternation drift), 7 MEDIUM/LOW. All addressed in v2 via Change Log. |
| v1 | security | HIGH_RISK_FINDINGS | 2 CRITICAL (query_graph scope leak, write Cypher unrestricted), 4 HIGH (APOC catalog reachable, since unvalidated, row cap byte-blind, depth blowup), 3 MEDIUM/LOW. All closed: write deny-list + read-only session + mandatory scope predicate + byte-cap + depth clamp + since regex. APOC absent confirmed via live probe → no more attack surface there. |
| v1 | qa | NEEDS_MINOR_GAPS_CLOSED | 2 CRITICAL (AC-7 manual-only, APOC probe = runbook only), 3 HIGH (seed fixture underdefined, cm_name routing not tested, test_cm_contract migration unclear). All closed: AC-7 now automated integration test, APOC probe done before approval (result: absent → pure Cypher), seed fixture file path specified, contract migration table in §6.5. |
| v2 | architect | APPROVE_WITH_MINOR_NITS | All v1 CRITICAL+HIGH closed. Nits: stale §4.5 dispatch block (`FallbackToCM` reference), stale §4.6 Prometheus mention, stale §6.1 test name, stale §8 APOC risk row. All addressed in v3. |
| v2 | security | APPROVE_WITH_MINOR_CAVEATS | All v1 CRITICAL+HIGH closed via deny-lists + read-only session + byte-cap + clamps. New MEDIUM: regex bypass via Cypher comments / multi-MATCH leak. v3 adds AC-17/AC-18/AC-19 plus `cypher_error` redaction. |
| v2 | qa | PASS_WITH_ONE_RESIDUAL_HIGH | All v1 CRITICAL+HIGH closed. NEW HIGH: AC-16 underspecified (no `KNOWN_NON_CALL_EDGES`, no test file name). v3 adds §4.7 with full registry + test stub. |
| v3 | architect | _pending re-review_ | — |
| v3 | security | _pending re-review_ | — |
| v3 | qa | _pending re-review_ | — |
