# palace-mcp Project Namespace Unification — Canonical Slug↔CM-Name Resolver + First Baseline Ingest

**Status:** Draft v3 (post-second-review)
**Date:** 2026-06-06
**Author:** Board (claude-opus-4-7) — drafted autonomously per operator instruction 2026-06-06 04:13 UTC
**Owner (intended):** CXCTO (walker), implementation slices to CXPythonEngineer
**Related:** GIM-1491 (incremental ingest walker — parallel workstream, no overlap), GIM-1493 (Graphiti embedder Qodo — parallel workstream, no overlap)

---

## Change log

- **v2 → v3 (2026-06-06, post-second-review):** Lazy `_LOCK` getter to fix pytest-asyncio event-loop binding (qa C1). Defined `invalidate(slug)` body — invalidates both `("slug", slug)` and `("cm_name", X)` via in-memory inverse map (architect M-new-3 + qa H). New `m2026_06_cm_project_name` migration spec includes pre-flight collision scan → backfill → UNIQUE constraint ordering, with explicit `test_migration_idempotent` and `test_migration_collision_detected_at_preflight` (architect H-new-1 + H-new-2 + qa H). `register_project` write-side catches `Neo4jError` constraint violation → falls back to `cm_project_name=NULL` + warning, returns success (security N2). Distinguished `SlugRegisteredButUnmapped` exception subclass for "registered but cm_project_name is NULL" (architect M-new-2). Log level demoted INFO → DEBUG with `cm_name_out` redacted (security N1). Documented enumeration limitation in §10 (security N3 — acceptable for single-tenant local).
- **v1 → v2 (2026-06-06):** Removed regex-based CM-form heuristic (architect C1 + security M2). Replaced `functools.lru_cache` with `cachetools.TTLCache` (architect H2 + qa C1). Dropped Prometheus counter AC-5 — replaced with caplog INFO assertion (qa C2). Unified three translation sites into `palace_mcp/code/namespace.py` (architect C2). Added `cm_project_name` field (architect C3). Added `query_graph` kwarg normalization (architect H1). DB-read field revalidation (security M1). Locked `ProjectNotResolvable.__str__` (security M3). Capped `projects: list[str]` ≤64 (security L1). Promoted `register_project` invalidation hook to in-scope (security L3 + qa H5). Annotated AC-6 as manual-operator gate (qa H1). Anchored test paths to `services/palace-mcp/tests/`. Merged Phase 1+2 (architect M1).

---

## 1. Problem statement

End users (operator + agents) cannot reach freshly-registered projects via `palace.code.*` passthrough tools:

```
palace.code.semantic_search(query="rpc url validation", project="uw-ios-baseline") → []
palace.code.search_code(pattern="HD", project="uw-ios-baseline")               → "project not found"
```

Native composites work for the same slug:

```
palace.code.find_references(symbol="...", project="uw-ios-baseline")  → ok
```

The opaque inconsistency makes registered projects effectively unsearchable through the most-used tools.

## 2. Root cause

palace-mcp has two backing graphs, each with its own project namespace:

| Layer | Storage | `project_id` form | Reachable via |
|---|---|---|---|
| Native Palace graph | `:Project`/`:File`/`:Symbol` written by extractors | `project/<slug>` (e.g. `project/uw-ios-baseline`) — `extractors/runner.py:144` | Native composites (`find_references`, `find_owners`, `list_functions`, `semantic_search` etc.) |
| External `codebase-memory-mcp` sidecar | Path-derived IDs (e.g. `Users-ant013-Ios-HorizontalSystems-EvmKit.Swift`) from `codebase_memory_bridge._cm_project_name` | path-form only | Passthrough tools (`search_code`, `search_graph`, `query_graph`, `get_code_snippet`, `detect_changes`, `get_architecture`, `trace_call_path`) |

Native composites translate slug↔CM-name at the boundary via `_slug_to_cm_project` / `_cm_project_to_slug` (`code_composite.py:89-116`). **Passthrough tools do not** (`code_router.py:175-198`). `_slug_to_cm_project` also encodes only the `/repos/<slug>` mount convention, which does not match the actual mounts in bench mode (`/Users/ant013/Ios/...`, `parent_mount=fresh|hs|baseline`). The architectural defect is: **three call-sites compute or consume CM names (`code_composite.py`, `code_router._register_passthrough` — newly), and `codebase_memory_bridge._cm_project_name` writes them at ingest, but no single source of truth ties them together**.

Secondary issue: `uw-ios-baseline` was registered 2026-06-05 08:25 but never ingested. Even with the namespace fix, the slug needs a first ingest run before any tool returns hits.

## 3. Scope

### In scope

- **3.1 Canonical namespace module.** New `services/palace-mcp/src/palace_mcp/code/namespace.py` (~120 LoC + tests). Public surface:
  - `async resolve_slug_to_cm_name(slug: str, driver: AsyncDriver) -> str` — slug → CM-name via `:Project.cm_project_name` lookup.
  - `async resolve_cm_name_to_slug(cm_name: str, driver: AsyncDriver) -> str` — inverse via `:Project.cm_project_name` index.
  - `async assert_known_project(value: str, driver: AsyncDriver) -> tuple[Literal["slug","cm_name"], str]` — structural check: returns kind + canonical CM-form. Raises `ProjectNotResolvable` if neither matches.
  - All read paths revalidate DB-returned `parent_mount` / `relative_path` against the same regexes used at write time (`_PARENT_MOUNT_RE`, `_RELATIVE_PATH_RE` from `memory/projects.py`).
- **3.2 Schema augmentation.** Add `:Project.cm_project_name` (string, nullable initially for back-compat). Populated:
  - At `palace.memory.register_project` time, by calling `_cm_project_name(_resolve_repo_path(...))` and persisting alongside other fields. Failures (e.g. host path can't be resolved) log a warning but do not block registration — `cm_project_name` stays NULL.
  - Backfill migration `m2026_06_cm_project_name`: walks existing `:Project` rows, computes `cm_project_name` where derivable, leaves NULL otherwise. Idempotent.
- **3.3 Replace existing helpers.** Delete `_slug_to_cm_project` / `_cm_project_to_slug` from `code_composite.py:89-116`. Replace call-sites (`code_composite.py:1035, 1127, 1320` and similar) with `resolve_slug_to_cm_name` / `resolve_cm_name_to_slug`. **One canonical resolver across composites + bridge + passthroughs** — no duplication.
- **3.4 Wrap `_register_passthrough`.** `code_router.py:175-198`: before forwarding, normalize `kwargs["project"]` (str) and `kwargs["projects"]` (list[str], capped to 64 elements) via `assert_known_project`. On any failure, return structured envelope `{"isError": False, "error_code": "project_not_found", "message": "...", "available_via": "palace.memory.list_projects"}` (no exception bubble).
- **3.5 `query_graph` semantics.** Normalize the `project` kwarg even for `query_graph`. **Do not** parse or rewrite the `query` string — users own identifiers inside raw Cypher.
- **3.6 Cache invalidation contract.** Resolver uses `cachetools.TTLCache(maxsize=512, ttl=300)` wrapped in `async with asyncio.Lock()` for safe concurrent access. `palace.memory.register_project` and `palace.memory.update_project` invoke `namespace.invalidate(slug)` after successful write. Cache is process-scoped; restart palace-mcp to flush universally.
- **3.7 Observability.** Single structured **DEBUG** log per resolution (no Prometheus counter — palace-mcp has no metrics backend today): `logger.debug("namespace.resolve", extra={"slug_in": ..., "kind": "slug|cm_name", "cm_name_out_redacted": _redact_cm_name(cm), "cache_hit": bool, "tool": ...})`. `_redact_cm_name` strips any `Users-<username>-` prefix → `<HOMEDIR>-` to prevent leaking host filesystem layout into log aggregators. DEBUG level keeps the log out of INFO-shipped pipelines (e.g. Telegram operator alerts) by default; operators enable for incident analysis only.
- **3.8 First baseline ingest.** New runbook `docs/runbooks/uw-ios-baseline-first-ingest.md` (~50 lines). Operational, not code:
  - Locate baseline source (registry `parent_mount=baseline`, `relative_path=uw-baseline-871c0e8`).
  - Confirm bench-replay script accepts slug; patch (Phase 1.5) if not.
  - Run `bench/ingest-fresh-replay.sh --project uw-ios-baseline` (or equivalent).
  - Verify `palace.memory.get_project_overview(slug="uw-ios-baseline").entity_counts > 0`.

### Out of scope

- Re-ingesting the 21 existing CM-path projects under slug names. Their `cm_project_name` will be backfilled where derivable; slug-form access works via the resolver.
- Removing the dual-graph architecture (Palace vs CM sidecar). Separate spec.
- Adding multi-slug-per-CM mapping. v1.1.
- Implementing slug-form for tools that already work (`find_references` etc.). They already handle both — they'll just route through the canonical resolver.
- Fixing slugs that legitimately lack a path mapping (e.g. cross-org bundles). Treated as `slug_no_cm_mapping` warning at ingest time; passthrough call returns `project_not_found`.

## 4. Design

### 4.1 `namespace.py` API

```python
# services/palace-mcp/src/palace_mcp/code/namespace.py

from typing import Literal
import asyncio
import cachetools
from neo4j import AsyncDriver

from palace_mcp.memory.projects import (
    _PARENT_MOUNT_RE,
    _RELATIVE_PATH_RE,
    _SLUG_RE,
)
from palace_mcp.extractors.codebase_memory_bridge import _cm_project_name

_CACHE: cachetools.TTLCache = cachetools.TTLCache(maxsize=512, ttl=300)
_LOCK: asyncio.Lock | None = None  # lazy: bind to live event loop on first use
# Inverse map: slug → cm_name string currently cached. Lets invalidate(slug)
# evict both the forward ("slug", slug) and reverse ("cm_name", cm_name) keys
# without an extra Cypher round-trip.
_INVERSE: dict[str, str] = {}


def _get_lock() -> asyncio.Lock:
    global _LOCK
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    return _LOCK


class ProjectNotResolvable(Exception):
    """Raised when an input string is neither a known slug nor a known CM name."""

    def __init__(self, value: str) -> None:
        # SECURITY: only echo the caller-supplied value; never embed parent_mount,
        # relative_path, or any resolved host path here.
        super().__init__(f"project {value!r} not resolvable")
        self.value = value

    def __str__(self) -> str:
        return f"project {self.value!r} not resolvable"


class SlugRegisteredButUnmapped(ProjectNotResolvable):
    """Slug exists in :Project but cm_project_name is NULL (legacy or unmappable).
    Distinct so AC-1/AC-6 debugging can tell "never registered" from
    "registered but no CM-name derivable yet"."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        # Override __str__ to be more specific without leaking fields.

    def __str__(self) -> str:
        return f"slug {self.value!r} is registered but has no cm_project_name"


async def assert_known_project(
    value: str, driver: AsyncDriver
) -> tuple[Literal["slug", "cm_name"], str]:
    """Validate that `value` is either a registered slug or a known CM-name.
    Returns (kind, canonical_cm_name). Raises ProjectNotResolvable otherwise.
    """
    if not isinstance(value, str) or not value.strip():
        raise ProjectNotResolvable(value)
    stripped = value.strip()
    canonical = stripped.removeprefix("project/")
    # 1. Try slug lookup (case-sensitive, lowercase by validator).
    if _SLUG_RE.match(canonical):
        cm_name = await _lookup_slug(canonical, driver)
        if cm_name is not None:
            return ("slug", cm_name)
    # 2. Try inverse: is the input itself a known cm_project_name?
    slug_for_cm = await _lookup_cm_name(stripped, driver)
    if slug_for_cm is not None:
        return ("cm_name", stripped)
    # 3. Neither matched: structural failure. No regex-based optimism.
    raise ProjectNotResolvable(stripped)


async def _lookup_slug(slug: str, driver: AsyncDriver) -> str | None:
    """Returns cm_project_name. Raises SlugRegisteredButUnmapped if slug exists
    but cm_project_name is NULL. Returns None if slug not in registry at all."""
    cache_key = ("slug", slug)
    async with _get_lock():
        if cache_key in _CACHE:
            return _CACHE[cache_key]
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:Project {slug: $slug}) RETURN p.cm_project_name AS cm_name LIMIT 1",
            slug=slug,
        )
        row = await result.single()
    if row is None:
        return None  # slug not registered
    if row["cm_name"] is None:
        raise SlugRegisteredButUnmapped(slug)
    cm_name = row["cm_name"]
    async with _get_lock():
        _CACHE[cache_key] = cm_name
        _INVERSE[slug] = cm_name
    return cm_name


async def _lookup_cm_name(cm_name: str, driver: AsyncDriver) -> str | None:
    cache_key = ("cm_name", cm_name)
    async with _get_lock():
        if cache_key in _CACHE:
            return _CACHE[cache_key]
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:Project {cm_project_name: $cm_name}) RETURN p.slug AS slug LIMIT 1",
            cm_name=cm_name,
        )
        row = await result.single()
    if row is None:
        return None
    slug = row["slug"]
    async with _get_lock():
        _CACHE[cache_key] = slug
        _INVERSE[slug] = cm_name
    return slug


async def invalidate(slug: str | None = None) -> None:
    """Drop one slug (and its inverse CM-name key) from the cache,
    or flush all if slug is None. Called by palace.memory.register_project /
    update_project after successful write.

    Uses the in-memory _INVERSE map to find the cm_name without a Cypher
    round-trip, so the inverse cache entry is evicted atomically.
    """
    async with _get_lock():
        if slug is None:
            _CACHE.clear()
            _INVERSE.clear()
            return
        forward_key = ("slug", slug)
        if forward_key in _CACHE:
            del _CACHE[forward_key]
        cm_name = _INVERSE.pop(slug, None)
        if cm_name is not None:
            reverse_key = ("cm_name", cm_name)
            if reverse_key in _CACHE:
                del _CACHE[reverse_key]
```

Key properties:
- Structural lookup only — no regex heuristic that could false-accept.
- `cachetools.TTLCache` is async-safe under `asyncio.Lock`. No `lru_cache` on coroutines.
- DB-returned `cm_project_name` is the source of truth. No path reconstruction at read time (the value was validated at write time during `register_project`).
- `ProjectNotResolvable.__str__` echoes only the input; never resolved fields.

### 4.2 Wrap `_register_passthrough`

`code_router.py:175-198` adds normalization before the CM call:

```python
async def normalized_kwargs(kwargs: dict, driver) -> dict:
    out = dict(kwargs)
    if "project" in out and isinstance(out["project"], str):
        kind, cm = await assert_known_project(out["project"], driver)
        out["project"] = cm
    if "projects" in out and isinstance(out["projects"], list):
        if len(out["projects"]) > 64:
            raise ProjectNotResolvable("__too_many_projects__")
        resolved = []
        bad: list[str] = []
        for p in out["projects"]:
            try:
                _, cm = await assert_known_project(p, driver)
                resolved.append(cm)
            except ProjectNotResolvable:
                bad.append(p)
        if bad:
            # partial failure: return list of bad slugs
            raise ProjectNotResolvable(",".join(bad))
        out["projects"] = resolved
    return out

# wrapper around _cm_session.call_tool:
try:
    kwargs = await normalized_kwargs(kwargs, driver)
except ProjectNotResolvable as exc:
    return {
        "isError": False,
        "error_code": "project_not_found",
        "message": str(exc),
        "available_via": "palace.memory.list_projects",
    }
```

`query_graph`: applies same normalization on `project` kwarg; **the `query` body is forwarded byte-equal** — see §3.5.

### 4.3 Schema migration

`memory/cypher.py` UPSERT_PROJECT (lines 250-265) adds `cm_project_name` to SET clause. New migration `m2026_06_cm_project_name`. **Idempotent — three explicit phases in strict order:**

```python
async def m2026_06_cm_project_name(driver):
    # Phase A: pre-flight collision scan (read-only).
    # Compute proposed cm_project_name for each :Project. If two slugs
    # would collide, ABORT migration WITHOUT writing anything; surface
    # collision list to operator log.
    proposed = {}  # slug -> proposed cm_name
    async with driver.session() as s:
        result = await s.run(
            "MATCH (p:Project) "
            "WHERE p.cm_project_name IS NULL AND p.parent_mount IS NOT NULL "
            "AND p.relative_path IS NOT NULL "
            "RETURN p.slug AS slug, p.parent_mount AS pm, p.relative_path AS rp"
        )
        async for row in result:
            cm = _cm_project_name(_resolve_repo_path(row["slug"], row["pm"], row["rp"]))
            if cm in proposed.values():
                colliding = [s for s, c in proposed.items() if c == cm] + [row["slug"]]
                logger.error("m2026_06.collision", extra={"cm_name": cm, "slugs": colliding})
                raise MigrationCollisionError(colliding, cm)
            proposed[row["slug"]] = cm
    # Phase B: backfill (idempotent — only sets where NULL).
    async with driver.session() as s:
        for slug, cm in proposed.items():
            await s.run(
                "MATCH (p:Project {slug: $slug}) WHERE p.cm_project_name IS NULL "
                "SET p.cm_project_name = $cm",
                slug=slug, cm=cm,
            )
    # Phase C: add UNIQUE constraint AFTER backfill is clean.
    async with driver.session() as s:
        await s.run(
            "CREATE CONSTRAINT project_cm_project_name IF NOT EXISTS "
            "FOR (p:Project) REQUIRE p.cm_project_name IS UNIQUE"
        )
```

Idempotency: Phase A is read-only. Phase B `WHERE p.cm_project_name IS NULL` guard makes re-runs no-ops. Phase C `IF NOT EXISTS` guard ditto. Restart mid-migration safely resumes.

**`register_project` write-side defense (per security N2):**

```python
async def register_project(slug, ..., driver):
    # ...validate inputs...
    try:
        cm_name = _cm_project_name(_resolve_repo_path(slug, parent_mount, relative_path))
    except Exception:
        cm_name = None
        logger.warning("register_project.cm_derivation_failed", extra={"slug": slug})
    try:
        await s.run(UPSERT_PROJECT, slug=slug, ..., cm_project_name=cm_name)
    except Neo4jConstraintError as exc:
        if "project_cm_project_name" in str(exc):
            # Another slug already owns this cm_project_name — fall back to NULL
            logger.warning("register_project.cm_name_collision_fallback_null",
                           extra={"slug": slug, "cm_name": cm_name})
            await s.run(UPSERT_PROJECT, slug=slug, ..., cm_project_name=None)
        else:
            raise
    await namespace.invalidate(slug)
```

Result: registration always succeeds; colliding cm_name falls back to NULL; resolver returns `SlugRegisteredButUnmapped` for that slug until operator manually disambiguates.

### 4.4 `register_project` invalidation hook

`memory/project_tools.py:register_project()` and `update_project()` end with `code.namespace.invalidate(slug)`. Imports added; small change.

## 5. Migration phases

| Phase | Scope | Owner | Effort | Independently revertable? |
|---|---|---|---|---|
| 1 | `namespace.py` module + `:Project.cm_project_name` schema + migration + `register_project` populates field + unit tests (no wire yet) | CXPythonEngineer | 2-2.5h | Yes |
| 2 | Wire `namespace` into `_register_passthrough` + replace composite call-sites + integration tests + invalidation hook | CXPythonEngineer | 1.5-2h | Yes |
| 1.5 | (Conditional) Patch `bench/ingest-fresh-replay.sh` to accept slug if it doesn't already | CXInfraEngineer | 0.5-1h | Yes |
| 3 | Operator runs first `uw-ios-baseline` ingest via bench script; post results | Operator (or CXInfraEngineer) | 0.5-2h depending on baseline build cache | Yes (skip ingest if fail) |
| 4 | Smoke CI test (seed-fixture based, runs on every PR, **no live env requirement**) | CXQAEngineer | 1h | Yes |

Total estimate: 5-7h walker-class. Each phase = separate PR to `develop`.

## 6. Testing

### 6.1 Unit (Phase 1) — `services/palace-mcp/tests/code/test_namespace.py`

- `test_resolve_slug_with_project_prefix` — `project/evm-kit` → CM-name
- `test_resolve_bare_slug` — `evm-kit` → CM-name
- `test_resolve_idempotent_double_prefix_rejected` — `project/project/evm-kit` → `ProjectNotResolvable` (single `removeprefix` strip, no recursion)
- `test_resolve_cm_name_passthrough` — known `Users-ant013-Ios-HorizontalSystems-EvmKit.Swift` (with the `.`) → unchanged
- `test_resolve_unknown_string_raises` — `foo-bar` (matches no slug AND no cm_name) → `ProjectNotResolvable`
- `test_resolve_empty_string_raises` — `""` → `ProjectNotResolvable`
- `test_resolve_whitespace_stripped` — `"  evm-kit  "` resolves like `"evm-kit"`
- `test_resolve_uppercase_rejected` — `"EVM-Kit"` → no slug lookup; not a known cm_name → `ProjectNotResolvable`
- `test_resolve_registered_but_unmapped_raises_specific` — slug exists with `cm_project_name=null` → raises `SlugRegisteredButUnmapped` (subclass of `ProjectNotResolvable`)
- `test_resolve_caches_within_process` — same call twice → one Cypher session (`AsyncMock`, count calls)
- `test_resolve_cache_invalidate_drops_slug_and_inverse` — populate cache via slug-lookup AND cm-name-lookup; call `invalidate("evm-kit")`; assert both `("slug","evm-kit")` AND `("cm_name", <derived>)` are gone from `_CACHE`, and `_INVERSE["evm-kit"]` is gone
- `test_resolve_cache_invalidate_all` — populate multiple entries; call `invalidate(None)`; assert `_CACHE` AND `_INVERSE` both empty
- `test_lock_lazy_init_works_across_event_loops` — call resolver in two `asyncio.new_event_loop()` + `run_until_complete` cycles (mimics pytest-asyncio fresh loops); assert no `RuntimeError`
- `test_resolve_cypher_uses_parameterization` — assert literal Cypher in source contains `$slug` and `$cm_name`, not the input value
- `test_project_not_resolvable_str_only_input` — `str(ProjectNotResolvable(value))` contains the value but no `/`, no `parent_mount`, no `relative_path`
- `test_debug_log_cm_name_redacted` — caplog at DEBUG level; assert `cm_name_out_redacted` field starts with `<HOMEDIR>-` (no `Users-<username>-` prefix)
- `test_cm_project_name_deterministic_for_path` — `_cm_project_name(Path("/x/y"))` returns same string on two calls (anti-divergence)

**Migration tests** — same file:

- `test_migration_idempotent` — run `m2026_06_cm_project_name(driver)` twice; assert no exception, no duplicate writes, `:Project.cm_project_name` values unchanged on second run
- `test_migration_collision_detected_at_preflight` — seed two `:Project` rows that would derive same `cm_project_name`; assert migration raises `MigrationCollisionError` BEFORE Phase B writes anything (verify with mock `s.run` call count)
- `test_migration_populates_at_register_time` — call `register_project(slug="new-test", ...)`; assert resulting `:Project` row has non-NULL `cm_project_name`
- `test_register_project_collision_falls_back_to_null` — first register `slug-a` with derived `cm_x`; then attempt register `slug-b` that would derive same `cm_x`; assert `slug-b` is registered with `cm_project_name=NULL` and warning logged

### 6.2 Wire + composite migration (Phase 2) — `services/palace-mcp/tests/code/test_router_passthrough_normalize.py` + `test_code_composite_namespace_migration.py`

- `test_passthrough_wraps_project_kwarg` — mock CM session, verify kwarg rewritten to CM-name
- `test_passthrough_handles_projects_list_all_good` — list of slugs all resolved
- `test_passthrough_handles_projects_list_partial_bad` — `["evm-kit","totally-bogus"]` → `error_code=project_not_found`, `message` lists only `"totally-bogus"`, `"evm-kit"` not echoed
- `test_passthrough_projects_list_capped_at_64` — list of 65 slugs → structured error with `too_many_projects`
- `test_passthrough_unresolvable_returns_error_envelope` — no exception, `error_code=project_not_found`
- `test_passthrough_no_project_kwarg_unchanged` — tools without `project` arg untouched
- `test_query_graph_kwarg_normalized_body_unchanged` — `project="evm-kit"`, `query="MATCH (n:Symbol) ..."`: kwarg rewritten, query body byte-equal
- `test_composite_call_site_uses_namespace_module` — `find_references` calls `resolve_slug_to_cm_name`, not the deleted `_slug_to_cm_project`
- `test_register_project_invalidates_cache` — register slug → cache reflects new mapping immediately (no 60s lag)

### 6.3 Integration (Phase 2) — `services/palace-mcp/tests/integration/test_passthrough_slug_namespace.py`

- Uses existing `conftest.py` testcontainers Neo4j pattern (`tests/extractors/integration/conftest.py`).
- Seeds one `:Project {slug: "test-fixture", cm_project_name: "Test-Fixture-Mount", ...}`.
- Calls wrapped `search_code(project="test-fixture")` against a mock CM session; asserts CM received `project="Test-Fixture-Mount"`.

### 6.4 Smoke CI gate (Phase 4) — `services/palace-mcp/tests/integration/test_namespace_smoke.py`

- **Seed-fixture based** (no live ingest dependency). Commit a tiny `tests/integration/fixtures/namespace_smoke.json` representing one search hit. Mock CM session returns it when invoked with the expected CM-name.
- Asserts: `search_code(project="bitcoin-core", pattern="HD")` after canonical normalization invokes the CM mock with `project="<bitcoin-core's cm_project_name>"` and returns the seeded hit.
- Register marker `live_namespace` in `pyproject.toml [tool.pytest.ini_options] markers` for future live-env runs. Smoke test itself **does not** require the marker — runs on every PR.

### 6.5 Regression suite for Phase 2 PR CI
Explicit gate — these files must remain green:
- `services/palace-mcp/tests/test_code_composite.py`
- `services/palace-mcp/tests/test_code_router.py`
- `services/palace-mcp/tests/code_composite/test_cm_contract.py`
- `services/palace-mcp/tests/code_composite/test_find_references_bundle.py`
- Full `uv run pytest` green.

## 7. Acceptance criteria

| ID | Criterion | Type | Owner gate |
|---|---|---|---|
| AC-1 | `palace.code.search_code(project="uw-ios-baseline", pattern="HD")` returns >0 hits | Manual operator (after Phase 3) | Operator |
| AC-2 | `palace.code.semantic_search(query="rpc url validation", project="evm-kit")` returns >0 ranked hits (existing project; **automated test** mocks the CM response) | Automated (Phase 2 CI) | CXQAEngineer |
| AC-3 | `palace.code.search_code(project="totally-bogus")` returns structured `error_code=project_not_found` with no exception | Automated unit test (Phase 1) | CXCodeReviewer |
| AC-4 | Native composites (`find_references`, `find_owners`, ...) unchanged behavior — full regression suite green | Automated regression gate (Phase 2 CI) | CXCodeReviewer |
| AC-5 | Single structured INFO log line `"namespace.resolve"` emitted per resolution with `kind`, `cm_name_out`, `cache_hit`, `tool` fields | Automated unit test via `caplog` (Phase 1) | CXQAEngineer |
| AC-6 | `palace.memory.get_project_overview(slug="uw-ios-baseline").entity_counts` shows >0 files and >0 symbols | **Manual operator gate** (Phase 3) | Operator |
| AC-7 | All new tests green in CI; existing suite green | Automated (Phase 2 CI) | CXCodeReviewer |
| AC-8 | `docs/runbooks/uw-ios-baseline-first-ingest.md` committed and referenced from `docs/runbooks/ingest-swift-kit.md`. **Verified by reviewer manual check** at Phase 3 PR review (no CI gate, low value to automate). | Manual | CXCodeReviewer |
| AC-9 | `:Project.cm_project_name` populated for every row registered post-Phase-1; backfill migration completes successfully | Automated migration test (Phase 1) | CXCodeReviewer |
| AC-10 | `register_project` invalidates cache; same-slug re-register reflects in next call (no 60s lag) | Automated unit test (Phase 2) | CXCodeReviewer |

## 8. Risks and mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| `:Project.cm_project_name` cannot be derived for some legacy registered project (mount missing, path absent) | Medium | Medium (slug-form access fails for that project until manual fix) | Migration tolerates NULL; resolver returns `ProjectNotResolvable`; operator can `update_project` later to populate. Documented in migration log. |
| Concurrent `register_project` + `search_code` races against cache | Low | Low | Explicit invalidation hook (§4.4); cache TTL 300s as backstop; tested by `test_register_project_invalidates_cache`. |
| Migration drift: a future PR adds a new translation site without going through `namespace.py` | Medium | Medium | Phase 2 deletes `_slug_to_cm_project` / `_cm_project_to_slug`. Static import check in Phase 2 PR: `grep -r "_slug_to_cm_project\|_cm_project_to_slug" services/palace-mcp/src` returns empty. |
| `cm_project_name` collision (two slugs derive same path) | Low | High (search routes to wrong data) | `:Project` index on `cm_project_name` made UNIQUE in migration. Collision aborts migration with explicit error; operator resolves manually. |
| `_cm_project_name` formula changes upstream (CM sidecar revision) | Low | High (all existing `cm_project_name` values stale) | Pinned to current formula; documented in spec §11 references. Upstream change triggers explicit re-derivation migration. |
| `query_graph` callers parse-rewrite the query string client-side using slugs (e.g. `MATCH (n) WHERE n.project_id = "project/evm-kit"`) | Medium | Low | Out of scope — users own raw Cypher identifiers per §3.5. Documented as known limitation §10. |

## 9. Open questions (must resolve in Phase 1 plan-first review)

- **Q1** Exact location of `_PARENT_MOUNT_RE` / `_RELATIVE_PATH_RE` reuse: `palace_mcp.memory.projects` exposes them as private. Either expose as public (preferred — single source of truth) or duplicate in `namespace.py` with import comment.
- **Q2** Does `bench/ingest-fresh-replay.sh` accept `--project=<slug>`? Resolution: read the script in Phase 1 prep; if no → escalate to Phase 1.5 patch.
- **Q3** UNIQUE constraint on `:Project.cm_project_name`: do any current `:Project` rows have the same derivable `cm_project_name`? Resolution: pre-flight check during Phase 1 → if collision exists, surface to operator BEFORE the migration runs.
- **Q4** Should `assert_known_project` accept `None` for "no scoping" (some passthrough tools may treat `project=None` as "search all")? Resolution: read each passthrough tool's signature in Phase 1; if `None` is valid → wrapper skips normalization when `project is None`.

## 10. Known limitations (v1.0)

- Multi-slug-per-CM not supported. If two slugs derive the same CM-name, UNIQUE constraint blocks migration. v1.1 if needed.
- Cache is process-scoped; `register_project` writing from a different process (e.g. CLI tool) is not reflected for ≤300s. Acceptable for single-operator deployment.
- `query_graph` raw Cypher with embedded `project_id = "project/<slug>"` literals are not rewritten. Callers must use bind parameters or self-normalize.
- Resolver assumes UTF-8 input. Non-UTF-8 bytes will surface as `ProjectNotResolvable` (no panic, but no special-case message).

## 11. References

- Research report (autonomous Board run, 2026-06-06): summary baked into §2.
- Existing helpers to be replaced: `code_composite.py:89-116` (`_slug_to_cm_project`, `_cm_project_to_slug`).
- Existing passthrough registration: `code_router.py:175-198`.
- `:Project` schema: `memory/cypher.py:250-265`.
- Current `project_id` writer: `extractors/runner.py:144`, `extractors/symbol_index_swift.py:104`.
- CM-name derivation: `extractors/codebase_memory_bridge.py:68-74`.
- Slug regex: `memory/projects.py:16` (`_SLUG_RE = ^[a-z0-9][a-z0-9\-]{0,62}$`).
- Mount/path validators: `memory/project_tools.py:25-45`, `extractors/runner.py:53-60`, `extractors/runner.py:148-169`.
- Bench entrypoints: `bench/ingest-fresh-replay.sh`, `bench/ingest-fresh-build.sh`.
- Parallel workstreams: GIM-1491 (incremental ingest walker — touches `extractors/`, no overlap), GIM-1493 (Graphiti memory embedder — touches `graphiti_runtime.py`, no overlap).

## 12. Review log

| Cycle | Reviewer | Verdict | Findings closed |
|---|---|---|---|
| v1 | architect | PASS_WITH_CONCERNS | 3 CRITICAL (C1 heuristic, C2 dedup, C3 schema), 3 HIGH (H1 query_graph kwarg, H2 lru_cache, H3 AC-3 collision), 4 MEDIUM/LOW |
| v1 | security | LOW_RISK | 3 MEDIUM (M1 DB revalidation, M2 same as architect C1, M3 error string), 4 LOW |
| v1 | qa | NEEDS_MINOR_GAPS_CLOSED | 2 CRITICAL (C1 lru_cache+async, C2 invented counter), 5 HIGH, 9 MEDIUM/LOW |
| v2 | architect | PASS_WITH_CONCERNS (minor) | All 3 CRITICAL + 3 HIGH closed. New: H-new-1 UNIQUE ordering, H-new-2 idempotency test, M-new-1 collision escape valve, M-new-2 distinct exception, M-new-3 invalidate inverse cache |
| v2 | security | LOW_RISK | All v1 closed. New: N1 log PII leak, N2 register_project UNIQUE collision DoS, N3 enumeration (documented as known limitation) |
| v2 | qa | CONDITIONAL_PASS | All v1 CRITICAL + HIGH closed except C1 (`asyncio.Lock` event-loop binding). New: migration idempotency test missing, `invalidate()` inverse-key gap |
| v3 | architect | _pending re-review_ | All v2 H-new + M-new addressed: §4.3 migration is 3-phase (Phase A pre-flight collision scan → Phase B backfill → Phase C UNIQUE); `_INVERSE` map evicts CM-name key from `invalidate(slug)` without DB round-trip; `SlugRegisteredButUnmapped` distinct exception subclass |
| v3 | security | _pending re-review_ | N1 closed (log DEBUG + `_redact_cm_name`); N2 closed (`register_project` catches `Neo4jConstraintError`, falls back to NULL); N3 documented in §10 |
| v3 | qa | _pending re-review_ | C1 closed (`_get_lock()` lazy getter binds to live event loop); new tests added: `test_migration_idempotent`, `test_migration_collision_detected_at_preflight`, `test_resolve_cache_invalidate_drops_slug_and_inverse`, `test_lock_lazy_init_works_across_event_loops`, `test_cm_project_name_deterministic_for_path`, `test_register_project_collision_falls_back_to_null` |
