---
slug: dependency-surface
status: proposed
branch: feature/GIM-191-dependency-surface
paperclip_issue: 191
authoring_team: Claude (Board+Claude brainstorm); Claude implements end-to-end
predecessor: 476acf07 (post-GIM-188 develop tip)
date: 2026-05-04
---

# GIM-191 — Dependency Surface Extractor (Phase 2 #5)

## 1. Context

**Roadmap reference**: `docs/roadmap.md` §2.1 item #5 "Dependency Surface Extractor" — Claude team, deterministic, tool stack `dependency-analysis-gradle-plugin + spmgraph + Package.resolved parser`. Status before this slice: 📦 (planned, not started).

**Phase 1 closed today (2026-05-04)** with merges of GIM-128 (Swift), GIM-184 (C/C++/Obj-C), GIM-182 (Multi-repo SPM ingest). GIM-186 (Git History Harvester, Phase 2 prereq) is in flight in parallel. This slice is a **second Phase 2 item starting in parallel** with GIM-186 because:

- It is independent of GIM-186 (no `:Commit` consumption).
- It is non-LLM (deterministic parse of structured manifests).
- It builds on GIM-182 — the bundle ingest landed `Package.resolved` parsing precedent (`services/palace-mcp/scripts/diff-manifest-vs-package-resolved.py`).
- It writes to the **already-existing** `:ExternalDependency` model in `extractors/foundation/models.py` (no extractor has used it yet — we are the first writer).

**Cross-cutting prereq alignment** (per `docs/research/extractor-library/report.md` §6 dedup hint): "#5 Dependency Surface + #39 Cross-Repo Version Skew (dedup via shared `:ExternalDependency` node)". This slice ships the schema + writer; #39 will reuse the same node-type later.

**Predecessor SHA**: `476acf07` (`develop` tip after GIM-188 merge).

**Authoring split**: Board + Claude session brainstorms spec + plan; Claude paperclip team implements end-to-end (per `docs/roadmap.md` §3 Claude queue + operator decision 2026-05-03).

**Related artefacts** (must read before implementation):
- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py:140` — `ExternalDependency` model (purl, ecosystem, resolved_version, group_id).
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py:60-62` — `ext_dep_purl_unique` constraint already defined.
- `services/palace-mcp/scripts/diff-manifest-vs-package-resolved.py` — reference parser for `Package.resolved` v2/v3 schema (top-level `pins` OR nested `object.pins`).
- `docs/superpowers/specs/2026-05-03-GIM-186-git-history-harvester-design.md` §3.5 Foundation extensions — pattern for extending foundation without breaking existing extractors.
- `docs/superpowers/specs/2026-04-27-101a-extractor-foundation-design.md` — `BaseExtractor`, `ExtractorRunContext`, `ensure_custom_schema`.
- `docs/research/extractor-library/outline.yaml:47-51` + `report.md:49,259` — research summary for #5.

## 2. v1 Scope (frozen)

### IN

1. **`dependency_surface` extractor** registered in `services/palace-mcp/src/palace_mcp/extractors/registry.py`.
2. **Pydantic v2 parsed-entry models** for SPM, Gradle, Python ecosystems. All `version` strings normalised; `purl` constructed per §6.
3. **Three sub-parsers**:
   - `parsers/spm.py` — reads `Package.swift` (declared) + `Package.resolved` (pinned versions). Schema v2/v3 supported.
   - `parsers/gradle.py` — reads `gradle/libs.versions.toml` (Gradle version catalog) + per-module `build.gradle.kts` (declared `implementation(libs.X)` references).
   - `parsers/python.py` — reads `pyproject.toml` (`[project.dependencies]`, `[project.optional-dependencies]`) + `uv.lock` (pinned versions).
4. **`:ExternalDependency` writes** via existing foundation model + UNIQUE constraint on `purl`. Idempotent `MERGE`.
5. **`:Project -[:DEPENDS_ON]-> :ExternalDependency` edges** with properties: `scope` (compile / test / runtime), `declared_in` (relative path of source file), `declared_version_constraint` (raw constraint string before resolution).
6. **purl construction conventions** (§6) — single source of truth.
7. **Per-project ingest scope**: `palace.ingest.run_extractor(name="dependency_surface", project="<slug>")`.
8. **Auto-detect manifest presence**: extractor scans the repo root for known manifest files; absence of all known formats = `nodes_written=0` with `dep_surface_no_manifests` warning event (not an error).
9. **Mini-fixture augmentation**: `services/palace-mcp/tests/extractors/fixtures/dependency-surface-mini-project/` with all three ecosystems represented (SPM `Package.swift` + `Package.resolved` with 2 deps; Gradle `libs.versions.toml` + `build.gradle.kts` with 2 deps; Python `pyproject.toml` + minimal `uv.lock` with 2 deps).
10. **Operator runbook** at `docs/runbooks/dependency-surface.md`.
11. **Live smoke**: gimle (Python) + uw-android (Gradle) on iMac. UW-iOS smoke deferred to F2 until iOS clone lands on iMac (currently not present per `/Users/Shared/Ios/unstoppable-wallet-ios` empty).

### OUT (deferred follow-ups)

| # | Deferred item | Reactivation trigger |
|---|---|---|
| F1 | CocoaPods `Podfile` / `Podfile.lock` parser | UW-iOS clone available + measurable gap on Pods-only deps |
| F2 | Live UW-iOS Package.swift smoke | Operator clones UW-iOS to `/Users/Shared/Ios/unstoppable-wallet-ios` |
| F3 | Transitive dependency graph (resolution closure) | First consumer queries "all transitive deps of X" |
| F4 | npm `package.json` / `package-lock.json` parser | First TS/JS project with non-trivial deps lands |
| F5 | Cargo `Cargo.toml` / `Cargo.lock` parser | First Rust project lands |
| F6 | Solidity (foundry/hardhat) dep manifests | UW-EVM contract dep tracking becomes a stated need |
| F7 | License field extraction | Compliance/audit consumer requests it |
| F8 | Dependency vulnerability cross-reference (OSV/GHSA) | Security consumer requests it |
| F9 | Module-level dep granularity (separate edges per module instead of per-project) | First consumer needs "what does module X specifically depend on" (vs "what does the project depend on") |
| F10 | `dependency-analysis-gradle-plugin` integration for usage-vs-declared diff | First consumer asks "which declared deps are unused" |

### Silent-scope-reduction guard

CR Phase 3.1 must paste:

```bash
git diff --name-only origin/develop...HEAD | sort -u
```

Output must match the file list declared in §4 verbatim. Any out-of-scope file → REQUEST CHANGES per `feedback_silent_scope_reduction.md`.

## 3. Architecture

### 3.1 Three-layer summary

1. **Storage**: Neo4j only (per ADR D2: structured nodes + edges in Neo4j; no Tantivy — there is no full-text body for deps). `:ExternalDependency` already namespaced via `purl` UNIQUE; `:Project -[:DEPENDS_ON]-> :ExternalDependency` edges carry per-edge metadata. Per-project group_id isolation.
2. **Ingest**: Single-phase per-project run:
   - Scan repo root for known manifest files (`Package.swift`, `Package.resolved`, `gradle/libs.versions.toml`, `**/build.gradle.kts`, `pyproject.toml`, `uv.lock`).
   - Parse each present format via its sub-parser → `list[ParsedDep]`.
   - MERGE each `ParsedDep` into `:ExternalDependency` (idempotent on `purl`).
   - MERGE each `(Project)-[:DEPENDS_ON]->(ExternalDependency)` edge with properties.
   - Emit JSONL events; return `ExtractorStats(nodes_written, edges_written)`.
3. **Query** (no new MCP tool in this slice): consumers use Cypher directly. Sample queries in §9.4 smoke gate.

**Why no Tantivy**: dep entries are structured (purl is essentially a key); there is no full-text body. Adding Tantivy would be over-engineering.

**Why single-phase**: deps are tens-to-thousands per project (UW-Android ~150 declared deps, UW-iOS ~50 SPM deps). Phase budgeting (per `check_phase_budget`) is unnecessary at this scale; full re-parse on every run is fine v1. Incremental refresh is F-followup.

### 3.2 Diagram

```
┌──────────────── iMac (Production) ──────────────────────────┐
│                                                              │
│  Local clones (already mounted via docker-compose.yml):      │
│    /repos/gimle/        — pyproject.toml + uv.lock           │
│    /repos/uw-android/   — gradle/libs.versions.toml +        │
│                            **/build.gradle.kts (multi-module)│
│    /repos-hs/<kit>/     — Package.swift + Package.resolved   │
│      (each HS Kit; deferred to F2 until uw-ios clone)        │
│                                                              │
│  palace-mcp container:                                       │
│    palace.ingest.run_extractor(name="dependency_surface",    │
│                                 project="gimle")             │
│      ↓                                                       │
│    Auto-detect manifests in /repos/<slug>                    │
│      ↓                                                       │
│    parse(spm) | parse(gradle) | parse(python)                │
│      ↓ list[ParsedDep]                                       │
│    Neo4j: MERGE :ExternalDependency on purl                  │
│           MERGE :Project-[:DEPENDS_ON]->:ExternalDependency  │
│      ↓                                                       │
│    ExtractorStats(nodes_written, edges_written)              │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Type contracts (Pydantic v2)

```python
# src/palace_mcp/extractors/dependency_surface/models.py
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Ecosystem = Literal["pypi", "maven", "gradle", "swift", "github", "cocoapods", "generic"]
Scope = Literal["compile", "runtime", "test", "build"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ParsedDep(FrozenModel):
    """One parsed dependency entry, ready for Neo4j MERGE.

    Maps to (:Project)-[:DEPENDS_ON {scope, declared_in, declared_version_constraint}]->
            (:ExternalDependency {purl, ecosystem, resolved_version, group_id}).
    """
    project_id: str          # "project/<slug>"
    purl: str                # see §6 for construction
    ecosystem: Ecosystem
    declared_version_constraint: str  # raw, pre-resolution (e.g. "^1.0.0", "[1.0,2.0)", "1.2.3")
    resolved_version: str             # pinned, or sentinel "unresolved" (per foundation/models.py:137)
    scope: Scope
    declared_in: str                  # relative path from project root, e.g. "app/build.gradle.kts"

    @field_validator("purl")
    @classmethod
    def _check_purl(cls, v: str) -> str:
        if not v.startswith("pkg:"):
            raise ValueError(f"purl must start with 'pkg:': {v!r}")
        return v

    @field_validator("resolved_version")
    @classmethod
    def _check_resolved(cls, v: str) -> str:
        if not v:
            raise ValueError("resolved_version must be non-empty (use 'unresolved' sentinel)")
        return v


class ManifestParseResult(FrozenModel):
    """What each sub-parser returns."""
    ecosystem: Ecosystem
    deps: tuple[ParsedDep, ...]
    parser_warnings: tuple[str, ...]   # non-fatal issues (e.g. "Package.resolved missing pin for X")


class IngestSummary(FrozenModel):
    project_id: str
    run_id: str
    deps_parsed: int               # total parsed across all ecosystems
    deps_written: int              # actually MERGEd (= deps_parsed minus duplicates within run)
    edges_written: int             # :DEPENDS_ON edges written
    ecosystems_present: tuple[Ecosystem, ...]
    parser_warnings_count: int
    duration_ms: int
```

### 3.4 Invariants

1. **purl uniqueness across runs and projects** — `:ExternalDependency` node uniqueness via `ext_dep_purl_unique` constraint (already in foundation `schema.py:60`). Same purl across UW-iOS-app and EvmKit-mini → single node, multiple `:DEPENDS_ON` edges from different `:Project` nodes.
2. **Per-project namespacing on edges** — `:DEPENDS_ON` edge carries project context via the source node `(:Project {slug: ...})`. The `ExternalDependency` node itself does NOT carry per-project state (its `group_id` field is set on first MERGE; subsequent re-runs from other projects do NOT overwrite it — this is the documented v1 behavior; cross-project provenance is F-followup).
3. **Resolved version sentinel** — when a manifest declares a version constraint without a lock-file pin, `resolved_version = "unresolved"` (per foundation `UNRESOLVED_VERSION_SENTINEL`). NEVER null/empty/None.
4. **Idempotent re-parse** — re-running the extractor on unchanged manifests produces zero net writes. MERGE on `purl` for the node and on `(scope, declared_in)` for the edge.
5. **No transitive resolution** — v1 emits only what's declared. Closure over `Package.resolved` transitive `pins` is F3 followup; trans deps are noisy and double-count.

## 4. Component layout

```
services/palace-mcp/src/palace_mcp/extractors/dependency_surface/
├── __init__.py                  (NEW ~10 LOC: re-export DependencySurfaceExtractor)
├── extractor.py                 (NEW ~140 LOC: DependencySurfaceExtractor(BaseExtractor))
├── models.py                    (NEW ~80 LOC: ParsedDep, ManifestParseResult, IngestSummary)
├── purl.py                      (NEW ~100 LOC: purl construction per §6 + parsing helpers)
├── neo4j_writer.py              (NEW ~90 LOC: Cypher MERGE patterns for :ExternalDependency + :DEPENDS_ON)
└── parsers/
    ├── __init__.py              (NEW ~5 LOC)
    ├── spm.py                   (NEW ~140 LOC: Package.swift regex + Package.resolved JSON)
    ├── gradle.py                (NEW ~160 LOC: tomli for libs.versions.toml + regex for implementation())
    └── python.py                (NEW ~120 LOC: tomli for pyproject + custom uv.lock parser)

services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py
                                 (EXTEND ~15 LOC: add :Project-DEPENDS_ON-:ExternalDependency
                                  index_spec for fast project→dep lookup; the constraint
                                  ext_dep_purl_unique is already there)

services/palace-mcp/src/palace_mcp/extractors/registry.py
                                 (EXTEND +2 LOC: import + register)

services/palace-mcp/src/palace_mcp/config.py
                                 (no extension — no new env vars; tomli is a stdlib of Python 3.11+)

services/palace-mcp/tests/extractors/
├── unit/
│   ├── test_dependency_surface_extractor.py     (NEW ~200 LOC)
│   ├── test_dependency_surface_purl.py          (NEW ~100 LOC, parametrized purl shapes)
│   ├── test_dependency_surface_parser_spm.py    (NEW ~140 LOC)
│   ├── test_dependency_surface_parser_gradle.py (NEW ~160 LOC)
│   ├── test_dependency_surface_parser_python.py (NEW ~120 LOC)
│   └── test_dependency_surface_models.py        (NEW ~70 LOC)
├── integration/
│   └── test_dependency_surface_integration.py   (NEW ~180 LOC, testcontainers Neo4j + fixture)
└── fixtures/
    └── dependency-surface-mini-project/         (NEW)
        ├── REGEN.md                             — synthetic regen instructions
        ├── Package.swift                        — 2 SPM deps (one GitHub, one direct URL)
        ├── Package.resolved                     — schema v3, pins for both
        ├── gradle/
        │   └── libs.versions.toml               — version catalog with 2 entries
        ├── app/
        │   └── build.gradle.kts                 — 2 implementation() declarations
        ├── pyproject.toml                       — 2 deps under [project.dependencies]
        └── uv.lock                              — minimal lock with 2 packages

CLAUDE.md                        (EXTEND ~15 LOC: §"Extractors" → add dependency_surface row + operator workflow)

docs/runbooks/
└── dependency-surface.md         (NEW ~120 LOC: setup + smoke + troubleshooting + Cypher query examples)
```

**Estimated size**: ~890 LOC prod + ~970 LOC test + spec + plan + runbook + fixture.

## 5. Data flow

### 5.1 Ingest pipeline

```python
# extractor.py — sketch (real run() against BaseExtractor contract)
class DependencySurfaceExtractor(BaseExtractor):
    name: ClassVar[str] = "dependency_surface"
    description: ClassVar[str] = "Parse dep manifests (SPM/Gradle/Python) → :ExternalDependency."

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver  # deferred (per symbol_index_python.py:67-104)
        driver = get_driver()
        if driver is None:
            raise ExtractorError(...)

        # 0. Pre-flight
        previous_error = await _get_previous_error_code(driver, ctx.project_slug)
        check_resume_budget(previous_error_code=previous_error)
        await ensure_custom_schema(driver)

        # 1. Auto-detect manifests
        spm_present = (ctx.repo_path / "Package.swift").is_file()
        gradle_present = (ctx.repo_path / "gradle" / "libs.versions.toml").is_file() or any(
            (ctx.repo_path / sub).rglob("build.gradle.kts") for sub in [""]
        )
        python_present = (ctx.repo_path / "pyproject.toml").is_file()

        if not (spm_present or gradle_present or python_present):
            ctx.logger.warning("dep_surface_no_manifests",
                               extra={"event": "dep_surface_no_manifests",
                                      "project_id": ctx.group_id})
            return ExtractorStats(nodes_written=0, edges_written=0)

        # 2. Parse each present ecosystem
        all_parsed: list[ParsedDep] = []
        warnings: list[str] = []
        ecosystems_present: list[Ecosystem] = []

        if spm_present:
            r = parse_spm(ctx.repo_path, project_id=ctx.group_id)
            all_parsed.extend(r.deps); warnings.extend(r.parser_warnings)
            ecosystems_present.append(r.ecosystem)
        if gradle_present:
            r = parse_gradle(ctx.repo_path, project_id=ctx.group_id)
            all_parsed.extend(r.deps); warnings.extend(r.parser_warnings)
            ecosystems_present.append(r.ecosystem)
        if python_present:
            r = parse_python(ctx.repo_path, project_id=ctx.group_id)
            all_parsed.extend(r.deps); warnings.extend(r.parser_warnings)
            ecosystems_present.append(r.ecosystem)

        # 3. Write
        nodes_written, edges_written = await write_to_neo4j(
            driver, all_parsed, project_slug=ctx.project_slug, group_id=ctx.group_id
        )

        # 4. JSONL summary event
        ctx.logger.info("dep_surface_complete",
                        extra={"event": "dep_surface_complete",
                               "project_id": ctx.group_id,
                               "deps_parsed": len(all_parsed),
                               "deps_written": nodes_written,
                               "edges_written": edges_written,
                               "ecosystems_present": ecosystems_present,
                               "parser_warnings_count": len(warnings)})

        return ExtractorStats(nodes_written=nodes_written, edges_written=edges_written)
```

### 5.2 Per-ecosystem parser sketches

**SPM** (`parsers/spm.py`):
```python
# Package.swift declared deps via regex over .package(url:from:) / .package(url:branch:) / .package(url:exact:):
# Pattern: \.package\(\s*url:\s*"(?P<url>[^"]+)"\s*,\s*(?P<kind>from|branch|exact|revision):\s*"(?P<ver>[^"]+)"
# Package.resolved JSON: top-level "pins" (v3) OR "object.pins" (v2);
# each pin has "location" (URL) and "state.version" (or "state.revision" for branch pins).
# Construct purl per §6.
```

**Gradle** (`parsers/gradle.py`):
```python
# 1. Read gradle/libs.versions.toml via stdlib tomllib (tomli for <3.11, but pyproject.toml says ^3.11).
# 2. Build a map: alias (e.g. "androidx.appcompat") → (group_id, name, version).
#    From [versions] table + [libraries] table; resolve "ref:..." against [versions].
# 3. Walk all build.gradle.kts files; regex for implementation\(libs\.([a-zA-Z._-]+)\) and friends
#    (api, kapt, annotationProcessor, testImplementation, compileOnly, runtimeOnly).
# 4. Each match → look up alias in step 2 map → emit ParsedDep.
# 5. scope mapping: implementation/api → "compile"; testImplementation → "test"; etc.
# 6. resolved_version = the version from libs.versions.toml (Gradle catalog is the lock — no separate lockfile in v1 scope).
```

**Python** (`parsers/python.py`):
```python
# 1. Read pyproject.toml [project.dependencies] (PEP 621 list of strings like "neo4j>=5.0").
#    Also [project.optional-dependencies] for scope="test" / "build".
# 2. Parse each entry via packaging.requirements.Requirement to get name + specifier.
# 3. Read uv.lock — TOML (already parsed by uv internally; stable schema; sample at gimle/uv.lock).
#    Build map: package_name → exact version.
# 4. Match pyproject names against uv.lock map; resolved_version = lock-pin OR "unresolved" if missing.
# 5. purl: pkg:pypi/<name>@<resolved_version> (URL-encoded name).
```

### 5.3 JSONL event schema

| `event` | Fields | When |
|---|---|---|
| `dep_surface_no_manifests` | `project_id` | None of the known manifest formats present in repo root |
| `dep_surface_parser_warning` | `project_id, ecosystem, message` | Sub-parser hits a recoverable issue (missing pin, unknown alias) — one event per warning |
| `dep_surface_complete` | `project_id, deps_parsed, deps_written, edges_written, ecosystems_present, parser_warnings_count` | After successful run |
| `dep_surface_failed` | `project_id, ecosystem, error_repr` | Per-ecosystem parse exception (other ecosystems still emit) |

## 6. purl construction (single source of truth)

Per [purl-spec](https://github.com/package-url/purl-spec) ECMA-427:

| Ecosystem | purl pattern | Example |
|---|---|---|
| Python (PyPI) | `pkg:pypi/<name>@<version>` | `pkg:pypi/neo4j@5.28.2` |
| Gradle (Maven Central via Gradle catalog) | `pkg:maven/<group>/<artifact>@<version>` | `pkg:maven/androidx.appcompat/appcompat@1.7.1` |
| SPM (GitHub-hosted) | `pkg:github/<owner>/<repo>@<resolved_version>` | `pkg:github/horizontalsystems/EvmKit.Swift@1.5.3` |
| SPM (non-GitHub) | `pkg:generic/<host>/<path>?vcs_url=<url>@<version>` | `pkg:generic/example.com/foo?vcs_url=https://example.com/foo.git@1.0.0` |
| CocoaPods (deferred F1) | `pkg:cocoapods/<name>@<version>` | `pkg:cocoapods/Alamofire@5.10.1` |

Rationale for SPM:
- purl-spec has no official `swift` type yet (as of 2026). Two viable options:
  - `pkg:github/<owner>/<repo>` for GitHub-hosted SPM packages — covers ~95% of UW-iOS SPM deps (HS Kits + community packages all on GitHub).
  - `pkg:generic/...?vcs_url=...` for non-GitHub SPM packages — covers the remaining ~5%.
- Avoiding the unofficial `pkg:swift/...` namespace prevents collision when purl-spec eventually standardises Swift.

URL→purl algorithm in `purl.py`:
```python
def spm_purl_from_url(url: str, version: str) -> str:
    # github.com/owner/repo[.git] → pkg:github/owner/repo@version
    m = re.match(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$", url)
    if m:
        return f"pkg:github/{m['owner']}/{m['repo']}@{version}"
    # fallback: generic with vcs_url
    encoded = urllib.parse.quote(url, safe="")
    return f"pkg:generic/spm-package?vcs_url={encoded}@{version}"
```

## 7. Configuration

No new env vars. The extractor uses only `ctx.repo_path` (provided by runner) and the standard `get_driver()` for Neo4j writes.

`pyproject.toml` already requires Python 3.13+, so `tomllib` (stdlib since 3.11) is available — no `tomli` dep added.

## 8. Acceptance criteria

1. **Extractor registered** — `palace.ingest.list_extractors()` shows `dependency_surface`. Verified by contract test.
2. **Pydantic v2 models with validators** — `purl` regex validation (must start with `pkg:`); `resolved_version` non-empty (sentinel allowed). Verified by `test_dependency_surface_models`.
3. **Schema bootstrap idempotent** — re-running after first run does NOT raise `SchemaDriftError`; `ext_dep_purl_unique` constraint exists. Verified by `test_dependency_surface_schema_bootstrap`.
4. **SPM parser correct** — synthetic `Package.swift` + `Package.resolved` v3 yields exactly 2 `ParsedDep`. Schema v2 `object.pins` also handled (parametrized test). Verified by `test_dependency_surface_parser_spm`.
5. **Gradle parser correct** — synthetic `gradle/libs.versions.toml` + `build.gradle.kts` yields exactly 2 `ParsedDep` with correct `scope` mapping (`implementation` → `compile`, `testImplementation` → `test`). Verified by `test_dependency_surface_parser_gradle`.
6. **Python parser correct** — synthetic `pyproject.toml` + `uv.lock` yields exactly 2 `ParsedDep` with resolved versions from lock. `[project.optional-dependencies]` entries get `scope="test"` (or "build" if dependency-group `dev`). Verified by `test_dependency_surface_parser_python`.
7. **purl construction matches §6** — parametrized test `test_dependency_surface_purl` covers: PyPI, Maven, SPM-GitHub, SPM-non-GitHub-fallback. ≥10 parametrized cases.
8. **Cross-project dedup** — running on two synthetic projects that both depend on `neo4j@5.28.2` produces a SINGLE `:ExternalDependency` node and TWO `:DEPENDS_ON` edges. Verified by `test_dependency_surface_integration::test_cross_project_dedup`.
9. **Idempotent re-run** — running twice on the same project produces 0 new nodes and 0 new edges (idempotent MERGE). Verified by `test_dependency_surface_integration::test_idempotent_remerge`.
10. **No-manifest case** — running on a project with no recognized manifests emits `dep_surface_no_manifests` event and returns `ExtractorStats(nodes_written=0, edges_written=0)`. Verified by `test_dependency_surface_extractor::test_no_manifests`.
11. **Resolved-version sentinel** — when `Package.swift` declares a `branch:` package and `Package.resolved` has only revision (not version), `resolved_version="unresolved"` and a `dep_surface_parser_warning` is emitted. Verified by `test_dependency_surface_parser_spm::test_branch_pin_unresolved`.
12. **JSONL events** — every event from §5.3 has at least one test asserting it fires under the right condition.
13. **Per-module 90% coverage** —
    `pytest --cov=palace_mcp.extractors.dependency_surface.extractor --cov-fail-under=90`,
    `--cov=palace_mcp.extractors.dependency_surface.purl --cov-fail-under=90`,
    `--cov=palace_mcp.extractors.dependency_surface.parsers --cov-fail-under=90`. All green.
14. **Lint / format / mypy / pytest gates** — `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src/`, `uv run pytest -q` all green.
15. **Live smoke on iMac** — operator-driven smoke per §9.4. **Mandatory: gimle ingest succeeds in <2 s; uw-android first run succeeds in <10 s; cross-project dedup verified via Cypher.** SSH-from-iMac evidence captured.
16. **CLAUDE.md updated** — §"Extractors" → new `dependency_surface` row + operator workflow section.
17. **Runbook present** — `docs/runbooks/dependency-surface.md` covers setup, full + incremental ingest, parser warnings interpretation, cross-project query examples, troubleshooting.
18. **Mini-fixture committed** with deterministic regen via `REGEN.md`.

## 9. Verification plan

### 9.1 Pre-implementation (CTO Phase 1.1)

1. Confirm branch starts from `476acf07`.
2. Confirm 101a foundation primitives (`BaseExtractor`, `ExtractorRunContext`, `ExternalDependency`, `ensure_custom_schema`) stable on develop.
3. Confirm `tomllib` usable (Python 3.13+ already required).
4. Confirm `packaging` package available (already a transitive dep via `uv` ecosystem).
5. Verify CLAUDE.md mount table for `gimle`, `uw-android` (smoke targets).

### 9.2 Per-task gates

Each implementation task ends with a green test target before next starts (per plan task list).

### 9.3 Post-implementation gates

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest -q
uv run pytest --cov=src/palace_mcp --cov-fail-under=85 -q
uv run pytest --cov=palace_mcp.extractors.dependency_surface.extractor --cov-fail-under=90 \
  tests/extractors/unit/test_dependency_surface_extractor.py -q
uv run pytest --cov=palace_mcp.extractors.dependency_surface.purl --cov-fail-under=90 \
  tests/extractors/unit/test_dependency_surface_purl.py -q
uv run pytest --cov=palace_mcp.extractors.dependency_surface.parsers --cov-fail-under=90 \
  tests/extractors/unit/test_dependency_surface_parser_*.py -q
uv run pytest tests/extractors/integration/test_dependency_surface_integration.py -m integration -v
```

All must exit 0. Output pasted verbatim in CR Phase 3.1 handoff comment per `compliance-enforcement.md` §"Scope audit" (integration directory MUST be in pytest scope per GIM-188 tightening).

### 9.4 Live smoke (Phase 4.1, on iMac)

QA executes on iMac via SSH per `feedback_pe_qa_evidence_fabrication.md`.

#### 9.4.1 Pre-flight

1. `ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'` — identity capture.
2. Confirm `gimle` and `uw-android` parent_mounts are live in `docker-compose.yml`.
3. Restart palace-mcp via `docker compose --profile review up -d --force-recreate palace-mcp` (after merge).

#### 9.4.2 Smoke procedure (real `mcp.ClientSession.call_tool`)

```python
# scripts/smoke_dependency_surface.py — bundled in this slice
import asyncio, json, os, sys
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

PALACE_MCP_URL = os.environ.get("PALACE_MCP_URL", "http://localhost:8080/mcp")

async def call(session: ClientSession, tool: str, args: dict) -> dict:
    result = await session.call_tool(name=tool, arguments=args)
    return json.loads(result.content[0].text)

async def main() -> int:
    async with streamablehttp_client(PALACE_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            gimle_first   = await call(session, "palace.ingest.run_extractor",
                                       {"name": "dependency_surface", "project": "gimle"})
            gimle_second  = await call(session, "palace.ingest.run_extractor",
                                       {"name": "dependency_surface", "project": "gimle"})
            uw_first      = await call(session, "palace.ingest.run_extractor",
                                       {"name": "dependency_surface", "project": "uw-android"})
    print(json.dumps({"gimle_first": gimle_first, "gimle_second": gimle_second,
                       "uw_first": uw_first}, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

#### 9.4.3 Run smoke

```bash
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace && uv run python services/palace-mcp/scripts/smoke_dependency_surface.py' \
  | tee /tmp/dep-surface-smoke-$(date +%s).log
```

#### 9.4.4 Smoke gate (mandatory)

Smoke is GREEN iff ALL of the following:

- `gimle_first.success == true` AND `gimle_first.duration_ms < 2000`
- `gimle_first.nodes_written > 5` (palace-mcp has neo4j, graphiti-core, fastapi, ... — at least 5 deps)
- `gimle_second.nodes_written == 0` (idempotent re-run)
- `uw_first.success == true` AND `uw_first.duration_ms < 10000`
- `uw_first.nodes_written > 50` (UW-android has many androidx + retrofit + okhttp deps)
- Cross-project dedup gate via Cypher:
  ```cypher
  MATCH (p1:Project {slug:'gimle'})-[:DEPENDS_ON]->(d:ExternalDependency)<-[:DEPENDS_ON]-(p2:Project {slug:'uw-android'})
  RETURN count(d) AS shared
  ```
  May be 0 (different ecosystems) — but the query must run without error and return a single row.
- `:ExternalDependency` constraint scope check:
  ```cypher
  MATCH (d:ExternalDependency) RETURN d.ecosystem AS eco, count(d) AS n ORDER BY n DESC
  ```
  Must show at least `pypi` and `maven` rows after both projects ingest.

Any failure → smoke RED → REQUEST CHANGES.

#### 9.4.5 Evidence

PR body `## QA Evidence` must include verbatim:

```
$ ssh imac-ssh.ant013.work 'date -u; hostname; uname -a'
<output — hostname matches expected iMac>

$ jq '.gimle_first, .gimle_second, .uw_first' /tmp/dep-surface-smoke-*.log
<full ExtractorStats for each>

$ ssh imac-ssh.ant013.work \
  'cat ~/.paperclip/palace-mcp.log | jq -c "select(.event | startswith(\"dep_surface_\"))"'
<all dep_surface_* events with full payload>

$ ssh imac-ssh.ant013.work 'docker compose --profile review exec neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD \
    "MATCH (d:ExternalDependency) RETURN d.ecosystem AS eco, count(d) AS n ORDER BY n DESC"'
<rows showing pypi + maven counts>
```

#### 9.4.6 Cleanup

Ingested data persists for production use. If smoke failed and operator wants retry:

```cypher
MATCH (p:Project {slug: $slug})-[r:DEPENDS_ON]->() DELETE r
MATCH (d:ExternalDependency) WHERE NOT (d)<-[:DEPENDS_ON]-() DELETE d
```

(Removes only this-project edges; orphan `:ExternalDependency` cleanup keeps the graph clean.)

## 10. Out of scope (deferred)

See §2 OUT table for reactivation triggers.

## 11. Risks and mitigations

- **Gradle KTS regex brittleness** — `implementation(libs.X)` matched via regex; complex DSL constructs (e.g. `dependencies { add("implementation", libs.X) }`) may be missed. Mitigation: parametrized test with 5+ variants of declaration syntax; emit `dep_surface_parser_warning` for any line that matches `implementation(` but not the canonical pattern.
- **`uv.lock` schema instability** — `uv.lock` is TOML but the schema is uv-version-dependent. Mitigation: parse defensively; fall back to `resolved_version="unresolved"` if a key is missing; pin to gimle's current `uv.lock` shape as fixture.
- **purl namespace clashes between projects** — same `pkg:github/foo/bar@1.0.0` from `uw-ios-app` and `EvmKit-mini`. By design the node is shared (#5+#39 dedup intent). The ExtDep's `group_id` field (set on first MERGE) may not reflect every project that depends on it; documented in §3.4 invariant 2.
- **Multi-module Gradle projects** — UW-android has `app/`, `core-mini/`, `components/icons-mini/` etc. Each `build.gradle.kts` declared deps emit separate `:DEPENDS_ON` edges with different `declared_in` paths. This produces high edge counts for monorepos. Acceptable v1; F9 followup adds per-module granularity if a consumer needs it.
- **No `Package.swift` resolution semantics** — we DO read `Package.swift` for declared, but resolution is taken from `Package.resolved`. If `Package.resolved` is missing, every dep gets `resolved_version="unresolved"`. Operator runs `xcodebuild -resolvePackageDependencies` separately when needed.
- **CocoaPods absence** — UW-iOS uses both SPM and CocoaPods (per fixture path `Pods/Foo`). v1 ignores CocoaPods (F1 followup); operator gets a ~5-10% gap on UW-iOS Pods deps. Acceptable since SPM dominates.
- **No license / vulnerability data** — F7 / F8. v1 is structural-only.

## 12. Rollout

1. **Phase 1.1 CTO Formalize** — verify spec + plan paths, swap any placeholders, reassign CR. Predecessor `476acf07`.
2. **Phase 1.2 CR Plan-first review** — APPROVE comment must restate the 5 key invariants from §3.4. Cross-team transcription drift guard.
3. **Phase 2 Implementation** — TDD through plan tasks.
4. **Phase 3.1 CR Mechanical** — including scope audit, per-module coverage gates (3 modules), `tests/integration/` in pytest scope (per GIM-188 tightening).
5. **Phase 3.2 OpusArchitectReviewer Adversarial** — required vectors:
   - purl collisions across projects (verify dedup invariant).
   - Gradle KTS regex coverage on weird syntactic variants.
   - `uv.lock` schema drift between current and a future uv version.
   - Concurrent ingest of two projects with overlapping deps (race on MERGE).
   - Edge MERGE semantics: same `(project, dep, scope)` but different `declared_in` path → separate edges (intentional? yes).
6. **Phase 4.1 QA Live smoke** on iMac with SSH-from-iMac evidence.
7. **Phase 4.2 CTO Merge**.

## 13. Open questions

- **Multi-module dep granularity for UW-android** — currently v1 emits per-Project edges with `declared_in` path. If the first consumer (e.g. #39 Cross-Repo Version Skew) needs per-module aggregation, F9 followup adds a `:Module` node-type. Default: stay per-project; revisit when a consumer files a concrete need.
- **CocoaPods coverage on UW-iOS** — F1 deferred. If operator clones UW-iOS to iMac and Pods deps prove non-trivial, kick off F1. Trigger: post-clone smoke shows >10 Pods deps not visible via SPM.
- **Transitive deps** — F3 deferred. Current emit is declared-only. First "all transitive deps of X" query from a consumer triggers F3. Default: stay declared-only — closure is noisy and double-counts in shared-graph context.
