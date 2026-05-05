---
title: Hotspot extractor — file-level Tornhill score + per-function complexity
slug: hotspot-extractor
date: 2026-05-04
status: proposed (rev2)
paperclip_issue: 195
predecessor_sha: 13f6b13a4
authoring: Board+Claude
team: Claude
roadmap_item: "#44 Code Complexity × Churn Hotspot"
roadmap_source: "docs/roadmap.md §2.3 Historical, row #44 (verified 2026-05-04 by Board+Claude)"
---

# Hotspot extractor (Roadmap #44)

## rev2 changelog (2026-05-04)

Operator pre-CR review surfaced D1–D10 + 4 minor items. Rev2 addresses all of them:

- **D1 (bug)** — `complexity_status='fresh'` is now explicitly SET in §5.5 Phase 1+3 Cypher. Without this, `find_hotspots` returned empty after first run.
- **D2 (enforcement)** — added acceptance #11 + new test `test_cross_extractor_file_isolation.py` that scans `extractors/hotspot/neo4j_writer.py` source for `SET f.project_id` / `SET f.path` patterns and fails if found. Code-level guard, not convention.
- **D3 (testability)** — §9.4 row 5 rewritten as direct Cypher count delta (option b). Acceptance #6 explicitly lives in unit/integration tests via `result.consume().counters` (option c).
- **D4 (timeout)** — added §5.6 Lizard timeout policy: drop batch + emit warning event, do not fail run. New env `PALACE_HOTSPOT_LIZARD_TIMEOUT_BEHAVIOR`.
- **D5 (atomic phases)** — added invariant 7: Phase 4/5 only run after Phase 1–3 succeed. Documented in §5.7.
- **D6 (list_functions edge cases)** — §7.2 now spells out the error matrix: registered+missing-file = success+empty, unregistered = error envelope.
- **D7 (window oversight)** — invariant 4 reworded to include "AND identical `complexity_window_days`".
- **D8 (plan parallel)** — plan is the immediate next deliverable in this same Board+Claude session (`docs/superpowers/plans/2026-05-04-GIM-195-hotspot-extractor.md`); CTO Phase 1.1 verifies BOTH spec + plan paths.
- **D9 (CLAUDE.md scope)** — added §2 IN line: "Update `CLAUDE.md ## Extractors` with hotspot operator workflow (env vars, git_history dependency, R4 trade-off)".
- **D10 (roadmap citation)** — added `roadmap_source` frontmatter pointing to exact location.
- **Minor (datetime type)** — §5.4 cites `:Commit.committed_at` as Neo4j `DATETIME` (per `git_history/neo4j_writer.py` MERGE Cypher).
- **Minor (fixture stop-list)** — §5.1 switches to `parts`-based check (`("tests","extractors","fixtures") subseq of rel.parts`) instead of substring.
- **Minor (lizard upper bound)** — §2 IN + §6 pin `lizard>=1.17.20,<2.0`.
- **Minor (find_hotspots dead-files)** — D1 fix + `complexity_status='fresh'` filter together exclude zeroed dead files automatically; no separate min_score gate needed.

## 1. Context

Roadmap §2.3 row #44 — Code Complexity × Churn Hotspot. Phase 1 closed
on develop@`13f6b13a4` after GIM-186 (`git_history`) merged, which
unblocked the historical-extractor cohort (#11/#12/#26/#32/#43/#44).
Per operator memory `project_next_claude_extractor_queue.md`, this is
the first Claude-team Phase 2 slice; #32 Code Ownership follows.

**Product question this slice answers**: «Which files in this project
are both complex AND change frequently?» — the canonical
"crime-scene" hotspot from Adam Tornhill (*Your Code as a Crime Scene*).
A file with high cyclomatic complexity AND high churn is the
maintenance risk worth investing in first.

**Source-of-truth artefacts already on develop:**

- `:File {project_id, path}` nodes — written by `git_history`
  extractor (`extractors/git_history/neo4j_writer.py:_MERGE_TOUCHED_CYPHER`)
- `(:Commit)-[:TOUCHED]->(:File)` edges — same writer
- Foundation: `BaseExtractor`, `ExtractorRunContext`, `ExtractorStats`,
  `ensure_custom_schema`, `Pydantic v2 frozen models` pattern

**Operator-facing queries this slice ships:**

1. (A) **File-level top-N** — `palace.code.find_hotspots(project, top_n=20, min_score=0.0)` →
   ranked list `(path, ccn_total, churn_90d, hotspot_score, computed_at, window_days)`.
2. (C1) **Per-function complexity in a file** —
   `palace.code.list_functions(project, path, min_ccn=10)` → list of
   `(name, start_line, end_line, ccn, parameter_count, nloc, language)`.

The operator picked A+C1 (per brainstorm 2026-05-04). C2 (precise
per-function churn — diff hunks intersected with symbol DEF line ranges)
is explicitly deferred (F1).

## 2. Scope

### IN (v1)

- New extractor `hotspot` registered in `EXTRACTORS` registry
- File walk via `Path.rglob` with stop-list (mirrors `dependency_surface`
  precedent)
- `lizard` (Python pkg, `lizard>=1.17.20,<2.0`) called per-file batch via
  subprocess; `--xml` output parsed; `--working_threads=1` to honor
  container resource discipline. Upper version bound until F3 reviews
  the dependency; lizard 2.x may change CLI/XML schema.
- Languages auto-detected by lizard from extension: Python, Java, Kotlin,
  Swift, TypeScript, JavaScript, Solidity, C/C++, Obj-C, Ruby, PHP, Scala.
  Lizard's per-language CCN accuracy varies — it counts canonical control-flow
  branches, but modern syntax (Kotlin coroutines, Swift `guard`, TS unions in
  type guards) may be slightly under- or over-counted. Acceptable for v1
  ranking; F3 is the trigger for per-language replacements.
- New `:Function` nodes with `(project_id, path, name, start_line)` UNIQUE
- New `(:File)-[:CONTAINS]->(:Function)` edges
- Extension of existing `:File` props with hotspot fields (cross-extractor
  coordination per §3.4 invariant 1)
- Single configurable churn window via env `PALACE_HOTSPOT_CHURN_WINDOW_DAYS`
  (default 90); window value stored on each `:File` for query reproducibility
- Tornhill log-log score computed at write time:
  `score = log(ccn_total + 1) * log(churn_count + 1)`
- Eviction round per run: `:Function` nodes for files no-longer-on-HEAD
  are deleted; `:File` props for those files are zeroed and tagged
  `complexity_status='stale'`
- MCP query tools: `palace.code.find_hotspots`, `palace.code.list_functions`
- Update `CLAUDE.md ## Extractors` with `hotspot` row + new
  "Operator workflow: Hotspot extractor" subsection (env vars,
  git_history dependency, R4 window-change trade-off, recommended run
  ordering: `git_history` then `hotspot`)
- Smoke (Phase 4.1) on `gimle` (Python) + `uw-android` (Kotlin/Java)

### OUT (deferred F1-Fn — explicit reactivation triggers)

| ID | Item | Reactivation trigger |
|----|------|----------------------|
| F1 | Symbol-level precise churn (C2) — diff hunk × symbol DEF line range | Operator requests `find_hotspots(symbol=...)` query |
| F2 | Multi-window storage (30d / 90d / 365d simultaneously) | Operator requests "trending vs steady-state" comparison |
| F3 | Per-language complexity tools (radon for Python, detekt for Kotlin, SwiftLint for Swift) | Lizard's Kotlin-as-Java approximation produces visibly wrong rankings on UW |
| F4 | Trend extractor — snapshot diff between two SHAs | Operator requests "hotspots that worsened since release X" |
| F5 | `:Function -[:LINKED_TO]-> :SymbolDef` bridge edge | F1 lands AND fuzzy-match confidence threshold tuning is needed |
| F6 | Refactor `:File` props into separate `:Hotspot` node | Cross-extractor write coupling causes incident |
| F7 | UNWIND-batched MERGE for `:Function` writes | Real-prod smoke on uw-android measures `>60s` consistently |
| F8 | Per-class complexity (not just per-function) — class-level WMC, etc. | Operator requests "list god-classes" type query |

## 3. Data model

### 3.1 `:File` extension (cross-extractor coordination with `git_history`)

| Property | Owner | Lifecycle | Type |
|----------|-------|-----------|------|
| `project_id` | git_history (first writer) | ON CREATE only | STRING |
| `path` | git_history (first writer) | ON CREATE only | STRING (posix, relative) |
| `ccn_total` | hotspot (override-each-run) | SET each run | INTEGER |
| `churn_count` | hotspot (override-each-run) | SET each run | INTEGER |
| `complexity_window_days` | hotspot (override-each-run) | SET each run | INTEGER |
| `hotspot_score` | hotspot (override-each-run) | SET each run | FLOAT |
| `complexity_status` | hotspot (override-each-run) | SET each run; `'fresh'` or `'stale'` | STRING |
| `last_complexity_run_at` | hotspot (override-each-run) | SET each run | DATETIME (tz-aware UTC) |

**Note on single-property design**: `churn_count` and `complexity_window_days`
are stored as separate properties (not a dynamic name like `churn_90d`).
The window value is the source of truth for *what* the count means.
Operators changing the window between runs simply override both properties —
no stale property leakage. F2 (multi-window storage) introduces a separate
node type when needed; the v1 design stays minimal.

### 3.2 `:Function` (new node, hotspot extractor only)

```cypher
:Function {
  project_id: STRING,                    // matches :File.project_id
  path: STRING,                          // matches :File.path
  name: STRING,                          // lizard's emitted function name (short, unqualified)
  start_line: INTEGER,                   // 1-based inclusive
  end_line: INTEGER,                     // 1-based inclusive
  ccn: INTEGER,                          // lizard cyclomatic complexity number
  parameter_count: INTEGER,              // lizard
  nloc: INTEGER,                         // lizard non-comment lines
  language: STRING,                      // lizard's detected language label
  last_run_at: DATETIME                  // tz-aware UTC; used by eviction round
}
```

### 3.3 Edges

```cypher
(:File)-[:CONTAINS]->(:Function)
```

No edges back to commits or other extractors' nodes in v1.

### 3.4 Invariants (CR Phase 1.2 must restate verbatim)

1. **Cross-extractor `:File` coordination** — hotspot extractor writes
   *only* the props listed in §3.1 as owner=hotspot. It never SETs
   `project_id` or `path`; it MERGEs on `(project_id, path)` and lets
   ON CREATE fall through if the node was first-written by `git_history`.
2. **Function uniqueness** — `(project_id, path, name, start_line)` is
   UNIQUE for `:Function`. Overloaded methods are disambiguated by
   `start_line`; nested closures with identical names are similarly
   disambiguated.
3. **Per-project namespacing** — every read and write filters on
   `project_id`. No cross-project queries in v1.
4. **Idempotent re-run** — re-running the extractor against the same
   repo state AND the same `PALACE_HOTSPOT_CHURN_WINDOW_DAYS` value
   must produce `nodes_created == 0 AND relationships_created == 0`
   (verified via `result.consume().counters` per `dependency_surface`
   precedent). Window-change between runs intentionally violates this
   invariant (see §12 R4); operators changing the window should expect
   `:File` props to be overwritten.
5. **Eviction sound** — for every `:File` whose `path` no longer exists
   on HEAD: `:Function` children DELETED; `:File` props
   `ccn_total=0`, `churn_count=0`, `hotspot_score=0`, set
   `complexity_status='stale'`. The `:File` node itself is NOT deleted
   (git_history may still reference it historically).
6. **Window fidelity** — `complexity_window_days` is stored per-`:File`
   on each write. Query tools read this property and surface it; they
   do NOT re-read env at query time.
7. **Atomic phase ordering** — Phase 4 (`evict_stale_functions`) and
   Phase 5 (`mark_dead_files_zero`) execute only if Phases 1–3 succeed
   without exception. No broad `try/except` may wrap inner phases. CR
   Phase 3.1 verifies via source-grep on `extractor.py:run()`.

### 3.5 Foundation extensions (writes via `ensure_custom_schema`)

```cypher
CREATE CONSTRAINT function_unique IF NOT EXISTS
  FOR (f:Function) REQUIRE (f.project_id, f.path, f.name, f.start_line) IS UNIQUE;

CREATE INDEX file_hotspot_score IF NOT EXISTS
  FOR (f:File) ON (f.project_id, f.hotspot_score);

CREATE INDEX function_path IF NOT EXISTS
  FOR (f:Function) ON (f.project_id, f.path);
```

The constraints/indexes are declared on the extractor class:

```python
class HotspotExtractor(BaseExtractor):
    constraints = [
        "CREATE CONSTRAINT function_unique IF NOT EXISTS "
        "FOR (f:Function) REQUIRE (f.project_id, f.path, f.name, f.start_line) IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX file_hotspot_score IF NOT EXISTS "
        "FOR (f:File) ON (f.project_id, f.hotspot_score)",
        "CREATE INDEX function_path IF NOT EXISTS "
        "FOR (f:Function) ON (f.project_id, f.path)",
    ]
```

`ensure_custom_schema` aggregates these and runs them idempotently.

## 4. Architecture

```
extractors/hotspot/
├── __init__.py
├── extractor.py          # HotspotExtractor(BaseExtractor)
├── models.py             # ParsedFile, ParsedFunction (Pydantic v2 frozen)
├── lizard_runner.py      # subprocess wrapper, batching, XML parsing
├── neo4j_writer.py       # MERGE :File props, MERGE :Function, eviction
└── churn_query.py        # single Cypher query for window churn
```

Plus MCP tool registration:

```
src/palace_mcp/code/
├── find_hotspots.py      # palace.code.find_hotspots
└── list_functions.py     # palace.code.list_functions
```

Both tools registered in `src/palace_mcp/server.py` alongside existing
`palace.code.*` tools.

## 5. Algorithm

### 5.1 File walk

Mirrors `dependency_surface/extractor.py:_walk` precedent. Fixture
exclusion is parts-based (not substring) to avoid false-matching paths
like `docs/tests/extractors/fixtures-policy.md`:

```python
_STOP_DIRS = frozenset({
    ".git", ".venv", ".gradle", ".kotlin", ".idea",
    "node_modules", "build", "dist", "target",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".tantivy", "__MACOSX",
})
_FIXTURE_STOP_PARTS = ("tests", "extractors", "fixtures")
_LIZARD_EXTENSIONS = frozenset({
    ".py", ".java", ".kt", ".kts", ".swift",
    ".ts", ".tsx", ".js", ".jsx",
    ".sol", ".cpp", ".cc", ".h", ".hpp", ".m", ".mm",
})

def _has_subseq(parts: tuple[str, ...], subseq: tuple[str, ...]) -> bool:
    for i in range(len(parts) - len(subseq) + 1):
        if parts[i:i + len(subseq)] == subseq:
            return True
    return False

def _walk(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in _LIZARD_EXTENSIONS:
            continue
        rel = p.relative_to(root)
        if any(part in _STOP_DIRS for part in rel.parts):
            continue
        if _has_subseq(rel.parts, _FIXTURE_STOP_PARTS):
            continue
        yield p
```

### 5.2 Lizard subprocess

Per-batch (50 files):

```bash
lizard --xml --working_threads=1 <file1> <file2> ... <fileN>
```

Output is parsed via `xml.etree.ElementTree`. Parsing produces:

```python
@dataclass(frozen=True)
class ParsedFunction:
    name: str
    start_line: int
    end_line: int
    ccn: int
    parameter_count: int
    nloc: int

@dataclass(frozen=True)
class ParsedFile:
    path: str  # repo-relative POSIX
    language: str  # lizard's detected label
    functions: tuple[ParsedFunction, ...]
    @property
    def ccn_total(self) -> int:
        return sum(f.ccn for f in self.functions)
```

### 5.3 Run flow (HotspotExtractor.run)

```python
async def run(self, *, graphiti, ctx) -> ExtractorStats:
    run_started_at = datetime.now(tz=timezone.utc)
    files = list(_walk(ctx.repo_path))
    parsed = []
    for batch in chunked(files, 50):
        parsed.extend(await lizard_runner.run_batch(batch, ctx.repo_path))

    alive_paths = {p.path for p in parsed}
    nodes_w, edges_w = 0, 0

    # Phase 1: write file complexity + functions
    for pf in parsed:
        n, e = await neo4j_writer.write_file_and_functions(
            graphiti.driver, ctx.project_slug, pf, run_started_at,
        )
        nodes_w += n; edges_w += e

    # Phase 2: fetch churn for alive files (single Cypher)
    churn_map = await churn_query.fetch_churn(
        graphiti.driver, ctx.project_slug,
        list(alive_paths), window_days=settings.hotspot_window_days,
    )

    # Phase 3: write churn + score
    for pf in parsed:
        churn = churn_map.get(pf.path, 0)
        score = log(pf.ccn_total + 1) * log(churn + 1)
        n, e = await neo4j_writer.write_hotspot_score(
            graphiti.driver, ctx.project_slug, pf.path,
            churn=churn, score=score, window_days=settings.hotspot_window_days,
            run_at=run_started_at,
        )
        nodes_w += n; edges_w += e

    # Phase 4: evict stale functions
    n, e = await neo4j_writer.evict_stale_functions(
        graphiti.driver, ctx.project_slug, run_started_at,
    )
    nodes_w += n; edges_w += e

    # Phase 5: mark dead files (in :File but not in alive_paths)
    n, e = await neo4j_writer.mark_dead_files_zero(
        graphiti.driver, ctx.project_slug, list(alive_paths), run_started_at,
    )
    nodes_w += n; edges_w += e

    return ExtractorStats(nodes_written=nodes_w, edges_written=edges_w)
```

### 5.4 Churn query (single round-trip)

```cypher
UNWIND $paths AS path
MATCH (f:File {project_id: $project_id, path: path})
OPTIONAL MATCH (c:Commit)-[:TOUCHED]->(f)
WHERE c.committed_at >= datetime($cutoff)
RETURN path, count(c) AS churn
```

`$cutoff = (run_started_at - timedelta(days=window)).isoformat()`. Type
contract: `:Commit.committed_at` is stored as Neo4j `DATETIME` by
`extractors/git_history/neo4j_writer.py:_MERGE_COMMIT_CYPHER` (Pydantic
`datetime` → driver-native `Datetime`); the `>=` comparison against
`datetime($cutoff)` is type-safe.

### 5.5 Writer Cypher (Phase 1, 3, 4, 5)

#### Phase 1 — `:File` props (basic) + `:Function` MERGE + `:CONTAINS` edge

Per-file in extractor loop. `complexity_status='fresh'` is SET here so
that `find_hotspots` (which filters on `'fresh'`) returns this file.

```cypher
MERGE (f:File {project_id: $project_id, path: $path})
SET f.ccn_total = $ccn_total,
    f.complexity_status = 'fresh',
    f.last_complexity_run_at = datetime($run_started_at)
WITH f
UNWIND $functions AS fn_in
MERGE (fn:Function {
  project_id: $project_id,
  path: $path,
  name: fn_in.name,
  start_line: fn_in.start_line
})
SET fn.end_line = fn_in.end_line,
    fn.ccn = fn_in.ccn,
    fn.parameter_count = fn_in.parameter_count,
    fn.nloc = fn_in.nloc,
    fn.language = fn_in.language,
    fn.last_run_at = datetime($run_started_at)
MERGE (f)-[:CONTAINS]->(fn)
```

Note: `f.ccn_total` is SET via plain `SET` (not `ON CREATE SET`) — the
hotspot extractor owns this property per §3.4 invariant 1, so override-
each-run is correct. `:File.project_id` and `:File.path` come from
`MERGE` key matching; we never SET them.

#### Phase 3 — `:File` churn + score

```cypher
MERGE (f:File {project_id: $project_id, path: $path})
SET f.churn_count = $churn,
    f.complexity_window_days = $window_days,
    f.hotspot_score = $score,
    f.complexity_status = 'fresh',
    f.last_complexity_run_at = datetime($run_started_at)
```

`complexity_status='fresh'` is re-asserted in Phase 3 (idempotent SET) so
that even if Phase 1 was somehow skipped via future refactor, the state
remains consistent.

#### Phase 4 — evict stale functions (only after Phase 1–3 succeed; see §5.7)

```cypher
MATCH (f:File {project_id: $project_id})-[:CONTAINS]->(fn:Function)
WHERE fn.last_run_at < datetime($run_started_at)
DETACH DELETE fn
```

#### Phase 5 — zero dead files

```cypher
MATCH (f:File {project_id: $project_id})
WHERE NOT f.path IN $alive_paths
  AND coalesce(f.ccn_total, 0) > 0
SET f.ccn_total = 0,
    f.churn_count = 0,
    f.hotspot_score = 0.0,
    f.complexity_status = 'stale',
    f.last_complexity_run_at = datetime($run_started_at)
```

No string-templated property names — `churn_count` and
`complexity_window_days` are stable; the window value is bound as a
query parameter where needed.

### 5.6 Lizard timeout policy

A single batch (50 files) may exceed `PALACE_HOTSPOT_LIZARD_TIMEOUT_S`
(default 30s) if it contains an outlier file (e.g., 5k+ LOC Compose-DSL
Kotlin file). Policy:

| Behavior | Default | Description |
|----------|:---:|-------------|
| `drop_batch` | ✓ | log warning event `hotspot_lizard_batch_timeout` with batch file list, skip batch, continue with next batch |
| `fail_run` | — | raise `ExtractorRuntimeError(error_code='lizard_timeout')`; whole run errored, finalized with stats so far |

Selected via `PALACE_HOTSPOT_LIZARD_TIMEOUT_BEHAVIOR` env var (default
`drop_batch`). One bad file should not kill the slice; F-followup
re-batches 1-by-1 if pattern persists. Skipped files are NOT considered
"alive" for eviction purposes — their existing `:File` rows are not
zeroed (they're not in `alive_paths`), but they are also not refreshed,
so their `complexity_status` remains whatever it was before this run.
Document this in the warning event payload for operator forensics.

### 5.7 Atomic phase ordering (invariant 7)

`run()` is structured so that Phases 4 (evict_stale_functions) and 5
(mark_dead_files_zero) execute **only if Phases 1–3 completed without
exception**. Python control-flow already enforces this (no `try/except`
around inner phases). Future refactors must NOT introduce broad
`try/except: pass` around Phase 1/2/3 because that would let eviction
run on incomplete write state — old `:Function` nodes for files that
failed to re-parse this run would be deleted incorrectly. CR Phase 3.1
must verify there is no such broad exception suppression in
`extractor.py:run()`.

## 6. Environment configuration

New entries in `PalaceSettings` (`config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PALACE_HOTSPOT_CHURN_WINDOW_DAYS` | `90` | Window for churn count (Tornhill recommends 90 or 180) |
| `PALACE_HOTSPOT_LIZARD_BATCH_SIZE` | `50` | Files per lizard subprocess invocation |
| `PALACE_HOTSPOT_LIZARD_TIMEOUT_S` | `30` | Per-batch subprocess timeout (seconds) |
| `PALACE_HOTSPOT_LIZARD_TIMEOUT_BEHAVIOR` | `drop_batch` | One of `drop_batch` / `fail_run`; see §5.6 |

## 7. MCP query tools

### 7.1 `palace.code.find_hotspots`

```python
@app.tool(name="palace.code.find_hotspots")
async def find_hotspots(
    project: str,
    top_n: int = 20,
    min_score: float = 0.0,
) -> list[dict]:
    ...
```

Cypher:

```cypher
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.hotspot_score, 0.0) >= $min_score
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN f.path AS path,
       f.ccn_total AS ccn_total,
       f.churn_count AS churn,
       f.hotspot_score AS hotspot_score,
       f.last_complexity_run_at AS computed_at,
       f.complexity_window_days AS window_days
ORDER BY f.hotspot_score DESC
LIMIT $top_n
```

Error envelope on `project_not_registered` reuses the canonical
`error_code` per GIM-188 wire-contract pattern; precise check
(`error_code == "project_not_registered"`), not tautological.

### 7.2 `palace.code.list_functions`

```python
@app.tool(name="palace.code.list_functions")
async def list_functions(
    project: str,
    path: str,
    min_ccn: int = 0,
) -> list[dict]:
    ...
```

Cypher:

```cypher
MATCH (f:File {project_id: $project_id, path: $path})-[:CONTAINS]->(fn:Function)
WHERE fn.ccn >= $min_ccn
RETURN fn.name AS name,
       fn.start_line AS start_line,
       fn.end_line AS end_line,
       fn.ccn AS ccn,
       fn.parameter_count AS parameter_count,
       fn.nloc AS nloc,
       fn.language AS language
ORDER BY fn.ccn DESC, fn.start_line ASC
```

#### Error matrix

| Input | Outcome | Response |
|-------|---------|----------|
| `project` not registered (no `:Project` row) | error envelope | `{"ok": false, "error_code": "project_not_registered", ...}` |
| `project` registered, `path` not present in any `:File` (typo, deleted file, hotspot extractor never ran) | success | `[]` (empty list) |
| `project` registered, `path` present but file has no `:Function` children (binary/unparseable file → ccn_total=0) | success | `[]` (empty list) |
| `project` registered, `path` present, functions exist, none meet `min_ccn` | success | `[]` (empty list) |

The same matrix applies to `find_hotspots`: only `project_not_registered`
is an error envelope; everything else is `[]`. Wire-contract tests must
cover ALL FOUR rows for each tool, not just the error path (per GIM-188
"tautological wire-contract assertions" feedback).

## 8. Foundation dependencies (must be on develop@predecessor_sha)

| Dependency | Source | Status |
|------------|--------|--------|
| `:File {project_id, path}` | `git_history` extractor | ✅ on `13f6b13a4` |
| `(:Commit)-[:TOUCHED]->(:File)` | `git_history` neo4j_writer | ✅ |
| `BaseExtractor`, `ExtractorRunContext`, `ExtractorStats` | `extractors/base.py` | ✅ |
| `ensure_custom_schema` | `extractors/foundation/schema.py` | ✅ |
| `lizard>=1.17.20` | new `services/palace-mcp/pyproject.toml` entry | NEW |

`lizard` is a pure-Python package with no native deps — installs cleanly
in slim docker image.

## 9. Verification

### 9.1 Phase 1.1 (CTO formalize)

1. Branch `feature/GIM-195-hotspot-extractor` HEAD descends from
   `13f6b13a4` (predecessor SHA). Verify via
   `git merge-base --is-ancestor 13f6b13a4 HEAD`.
2. Spec exists at the path matching this filename.
3. Plan exists at `docs/superpowers/plans/2026-05-04-GIM-195-hotspot-extractor.md`.
4. Frontmatter `paperclip_issue` matches the issue number assigned by
   operator at issue-creation time (swap `NN` for real digits).
5. Foundation primitives stable on branch (per §8).

### 9.2 Phase 1.2 (CR plan-first review)

CR APPROVE comment must restate the §3.4 invariants (**1–7** — including
the new invariant 7 added in rev2) verbatim and confirm every plan task
has concrete test+impl+commit triple.

### 9.3 Phase 3.1 (CR mechanical review)

Tooling gates:

```bash
uv run ruff check src/palace_mcp/extractors/hotspot/ src/palace_mcp/code/find_hotspots.py src/palace_mcp/code/list_functions.py
uv run ruff format --check src/palace_mcp/extractors/hotspot/ src/palace_mcp/code/find_hotspots.py src/palace_mcp/code/list_functions.py
uv run mypy src/
uv run pytest tests/extractors/unit/test_hotspot_*.py -v
uv run pytest tests/extractors/unit/test_cross_extractor_file_isolation.py -v
uv run pytest tests/extractors/integration/test_hotspot_integration.py -v
uv run pytest tests/integration/test_find_hotspots_tool.py tests/integration/test_list_functions_tool.py -v
gh pr checks <PR-NUMBER>
```

All must be GREEN. Per `feedback_cr_phase31_ci_verification.md`:
mandatory `gh pr checks` paste in APPROVE comment.

Per `feedback_silent_scope_reduction.md`: `git diff --name-only
origin/develop...HEAD` paste in APPROVE comment, cross-checked against
plan-spec'ed file count.

Additional CR Phase 3.1 verifications added in rev2:

- Source-grep on `extractor.py:run()` — must show NO broad `try/except`
  wrapping inner phase calls (invariant 7).
- Source-grep on `neo4j_writer.py` — must show NO `SET f.project_id` /
  `SET f.path` patterns on `:File` matches (invariant 1, also enforced
  by `test_cross_extractor_file_isolation.py`).
- Verify `CLAUDE.md` was updated (new "Operator workflow: Hotspot
  extractor" subsection present + `hotspot` row in registered extractors
  table).

### 9.4 Phase 4.1 (QA live smoke on iMac)

| # | Project | Command | Expected |
|---|---------|---------|----------|
| 1 | `gimle` | `palace.ingest.run_extractor("git_history", "gimle")` | `ok=true` (prereq for #2) |
| 2 | `gimle` | `palace.ingest.run_extractor("hotspot", "gimle")` | `ok=true`, `nodes_written>0`, `duration_ms<10000` |
| 3 | `gimle` | `palace.code.find_hotspots(project="gimle", top_n=5)` | 5 rows, sorted by `hotspot_score` DESC, top file is plausibly central (e.g. `services/palace-mcp/src/palace_mcp/server.py`) |
| 4 | `gimle` | `palace.code.list_functions(project="gimle", path="<top-file-from-#3>", min_ccn=5)` | non-empty, sorted by ccn DESC |
| 5a | `gimle` | Cypher: `MATCH (fn:Function {project_id:'gimle'}) RETURN count(fn) AS before; MATCH (f:File {project_id:'gimle'}) WHERE f.complexity_status='fresh' RETURN count(f) AS files_before, sum(f.hotspot_score) AS sum_score_before` | capture `before`, `files_before`, `sum_score_before` |
| 5b | `gimle` | `palace.ingest.run_extractor("hotspot", "gimle")` (re-run) | `ok=true`, response `nodes_written` may be ≥1 (writer accumulator); proceed to 5c |
| 5c | `gimle` | Same Cypher as 5a — capture `after`, `files_after`, `sum_score_after` | **Assert** `before == after` AND `files_before == files_after` AND `sum_score_before == sum_score_after` (idempotency invariant 4) |
| 6 | `uw-android` | `palace.ingest.run_extractor("git_history", "uw-android")` | `ok=true` |
| 7 | `uw-android` | `palace.ingest.run_extractor("hotspot", "uw-android")` | `ok=true`, `duration_ms<60000` |
| 8 | `uw-android` | `palace.code.find_hotspots(project="uw-android", top_n=10)` | top-10 includes plausible Compose / ViewModel / Activity Kotlin classes |

Per operator memory `feedback_pe_qa_evidence_fabrication.md`: QA must
post commit SHA + image SHA + actual MCP-tool response payloads (not
fabricated), and must not skip tests due to "scope OUT" claims that
contradict spec §2 IN.

## 10. Acceptance criteria

1. `hotspot` registered in `EXTRACTORS` registry; `palace.ingest.list_extractors()`
   shows it.
2. Extractor runs against `gimle` and `uw-android` fixtures and live repos
   without error.
3. `:File` props are populated correctly: `ccn_total`, `churn_count`,
   `hotspot_score`, `last_complexity_run_at`, `complexity_window_days`,
   `complexity_status`.
4. `:Function` nodes are created with `(project_id, path, name, start_line)`
   uniqueness enforced.
5. `(:File)-[:CONTAINS]->(:Function)` edges connect correctly.
6. Re-run with no source changes produces `nodes_created == 0 AND
   relationships_created == 0` measured via `result.consume().counters`
   in unit/integration tests. (Live smoke uses Cypher count delta per
   §9.4 row 5a/b/c — the MCP tool response's `nodes_written` is an
   accumulator and cannot be used for this assertion directly.)
7. Eviction round deletes `:Function` for files no longer on HEAD; zeroes
   `:File` props for those files.
8. `palace.code.find_hotspots(project, top_n)` returns ranked list with
   `window_days` echoed.
9. `palace.code.list_functions(project, path, min_ccn)` returns
   per-function metrics.
10. Wire-contract tests for both MCP tools include all four rows from
    §7.2 error matrix: success-with-results, success-with-empty-list
    (3 sub-cases), AND `error_code == "project_not_registered"`
    precise check (per GIM-188 feedback — no tautological assertions).
11. Cross-extractor `:File` isolation enforced by
    `tests/extractors/unit/test_cross_extractor_file_isolation.py` —
    statically scans `extractors/hotspot/neo4j_writer.py` source and
    fails if `SET\s+f\.project_id` or `SET\s+f\.path` regex matches
    appear on a `:File` MERGE clause. Code-level guard for
    invariant 1; not just convention.

## 11. Open questions (resolve before Phase 2)

- **Q1 — Lizard CCN accuracy on modern syntax**: Kotlin coroutines, Swift
  `guard`, TS type-guard unions, etc. may be under- or over-counted.
  Acceptable for v1 (relative ranking within a project still meaningful)?
  Or gate specific languages out of v1?
  **Tentative answer**: accept in v1; document in extractor docstring;
  F3 is the trigger for radon-Python + detekt-Kotlin + SwiftLint-Swift
  per-language replacement.
- **Q2 — `:Function.name` qualification**: lizard emits short names
  (`parseFunc`); SCIP-derived `:SymbolDef` (from `symbol_index_*`) has
  qualified names. F5 (linking) will need a fuzzy match. Document
  short-name choice in v1; do not pre-qualify.
- **Q3 — `git_history` not run** before `hotspot` for a project: hotspot
  will create `:File` nodes (first-writer-wins) with `churn=0`. Document
  recommended ordering in `extractors/README.md` and in CLAUDE.md
  Operator workflow section.

## 12. Risks

- **R1 — Lizard subprocess overhead** at 50k+ files (uw-android): 1000
  subprocess invocations × ~50ms each = ~50s. Within smoke gate (60s)
  but tight. Mitigation: F7 trigger if real-prod measures `>60s`.
- **R2 — Cross-extractor `:File` write coordination** — if a future
  extractor also writes to `:File`, ownership of new props must be
  documented at addition time. F6 (separate `:Hotspot` node refactor)
  is the safety valve.
- **R3 — Per-language CCN approximation** (Q1) — operator may find
  rankings surprising on Kotlin/Swift code that uses modern syntax.
  Mitigation: document up-front in `extractors/README.md`; F3 is the
  rewrite path with per-language tools.
- **R4 — Window change between runs**: re-run with a different
  `PALACE_HOTSPOT_CHURN_WINDOW_DAYS` will overwrite `churn_count`,
  `complexity_window_days`, and `hotspot_score` with values for the
  new window. Idempotency invariant 4 (zero net writes on re-run)
  holds only when the window is unchanged. Mitigation: document in
  `extractors/README.md`; F2 (multi-window storage) decouples windows
  cleanly when needed.
- **R5 — Lizard timeout on outlier files**: a single 5k+ LOC
  Compose-DSL or generated-source Kotlin file may exceed
  `PALACE_HOTSPOT_LIZARD_TIMEOUT_S` (default 30s) when batched with
  49 other files. Mitigation: §5.6 timeout policy defaults to
  `drop_batch` (skip + warn, do not fail run); operator can switch to
  `fail_run` if strict semantics required. F-followup: re-batch
  1-by-1 with raised timeout if same files repeatedly time out.
- **R6 — Cross-extractor `:File` write coordination** (concrete
  enforcement): convention alone (R2) breaks silently when a future
  Claude- or CX-team extractor unknowingly writes `SET f.project_id`
  on a `:File` MERGE. Mitigation: acceptance #11 + new test
  `test_cross_extractor_file_isolation.py` source-grep guard. CR
  Phase 3.1 also visually verifies. F6 (separate `:Hotspot` node
  refactor) remains the structural escape hatch.

## 13. How to start the phase chain

When operator approves the spec:

1. Operator creates paperclip issue (gets `GIM-N`).
2. Operator (or CTO) updates spec frontmatter `paperclip_issue: 195` →
   real number, renames spec/plan filenames to include `GIM-N`.
3. Atomic-handoff to **CTO** for Phase 1.1 Formalize per
   `paperclips/fragments/profiles/handoff.md`:
   - PATCH `status=in_progress + assigneeAgentId=<CTO-UUID> + comment`
     in one API call.
   - Use formal mention `[@CTO](agent://7fb0fdbb-...?i=eye)` in
     handoff comment.
4. CTO Phase 1.1 verification per §9.1.
5. CR Phase 1.2 must restate §3.4 invariants verbatim (transcription
   drift guard).
