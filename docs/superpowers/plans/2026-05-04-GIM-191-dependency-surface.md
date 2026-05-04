---
slug: dependency-surface
issue: GIM-191
spec: docs/superpowers/specs/2026-05-04-GIM-191-dependency-surface-design.md
predecessor: 476acf07
date: 2026-05-04
---

# GIM-191 — Dependency Surface Extractor — Implementation plan

TDD plan covering the `dependency_surface` extractor (Phase 2 §2.1 #5). Each
task ends with a green test target before the next starts. Phase mapping
follows `paperclips/fragments/shared/fragments/phase-handoff.md`.

## File structure

| Component | Files | Status |
|---|---|---|
| Models | `extractors/dependency_surface/models.py` | NEW |
| purl helpers | `extractors/dependency_surface/purl.py` | NEW |
| Extractor entry point | `extractors/dependency_surface/extractor.py` | NEW |
| Sub-parsers | `extractors/dependency_surface/parsers/{__init__,spm,gradle,python}.py` | NEW |
| Neo4j writer | `extractors/dependency_surface/neo4j_writer.py` | NEW |
| Re-export | `extractors/dependency_surface/__init__.py` | NEW |
| Schema extension | `extractors/foundation/schema.py` | EXTEND ~15 LOC |
| Registry | `extractors/registry.py` | EXTEND +2 LOC |
| Smoke | `services/palace-mcp/scripts/smoke_dependency_surface.py` | NEW ~80 LOC |
| Runbook | `docs/runbooks/dependency-surface.md` | NEW ~120 LOC |
| CLAUDE.md | EXTEND ~15 LOC | EXTEND |
| Mini-fixture | `tests/extractors/fixtures/dependency-surface-mini-project/` | NEW |
| Unit tests | `tests/extractors/unit/test_dependency_surface_*.py` (6 files) | NEW |
| Integration test | `tests/extractors/integration/test_dependency_surface_integration.py` | NEW |

13 files prod + 7 files test + spec + plan + runbook + fixture.

---

## Task 1: Pydantic v2 models

### Test (write first; must fail)

`tests/extractors/unit/test_dependency_surface_models.py`:

```python
def test_parsed_dep_purl_must_start_with_pkg():
    with pytest.raises(ValidationError):
        ParsedDep(project_id="project/x", purl="github/foo/bar@1.0",
                  ecosystem="github", declared_version_constraint="1.0",
                  resolved_version="1.0", scope="compile",
                  declared_in="Package.swift")

def test_parsed_dep_resolved_version_empty_rejected():
    with pytest.raises(ValidationError):
        ParsedDep(..., resolved_version="")

def test_parsed_dep_resolved_version_unresolved_sentinel_accepted():
    dep = ParsedDep(..., resolved_version="unresolved")
    assert dep.resolved_version == "unresolved"

def test_parsed_dep_frozen():
    dep = ParsedDep(...)
    with pytest.raises(ValidationError):
        dep.purl = "pkg:other/x@2.0"

def test_manifest_parse_result_carries_warnings():
    r = ManifestParseResult(ecosystem="pypi", deps=(), parser_warnings=("missing pin",))
    assert r.parser_warnings == ("missing pin",)
```

### Impl

Write `extractors/dependency_surface/models.py` per spec §3.3. Use
`ConfigDict(frozen=True, extra="forbid")`. Validators on `purl` and
`resolved_version`.

### Commit

`feat(GIM-191): Pydantic v2 models for dependency-surface extractor`

### Acceptance

`uv run pytest tests/extractors/unit/test_dependency_surface_models.py -v` →
all green.

---

## Task 2: purl construction

### Test (write first)

`tests/extractors/unit/test_dependency_surface_purl.py` — parametrized over
≥10 cases:

```python
@pytest.mark.parametrize("ecosystem,name,version,extras,expected", [
    ("pypi",  "neo4j",                              "5.28.2",  {},                  "pkg:pypi/neo4j@5.28.2"),
    ("pypi",  "graphiti-core",                      "0.28.2",  {},                  "pkg:pypi/graphiti-core@0.28.2"),
    ("maven", "androidx.appcompat:appcompat",       "1.7.1",   {},                  "pkg:maven/androidx.appcompat/appcompat@1.7.1"),
    ("maven", "com.squareup.retrofit2:retrofit",    "3.0.0",   {},                  "pkg:maven/com.squareup.retrofit2/retrofit@3.0.0"),
    ("github", "horizontalsystems", "EvmKit.Swift", "1.5.3",   {},                  "pkg:github/horizontalsystems/EvmKit.Swift@1.5.3"),
])
def test_purl_construction(ecosystem, name, version, extras, expected):
    assert build_purl(ecosystem=ecosystem, name=name, version=version, **extras) == expected

def test_spm_url_to_purl_github():
    assert spm_purl_from_url("https://github.com/horizontalsystems/EvmKit.Swift.git", "1.5.3") \
           == "pkg:github/horizontalsystems/EvmKit.Swift@1.5.3"

def test_spm_url_to_purl_github_no_dot_git():
    assert spm_purl_from_url("https://github.com/horizontalsystems/EvmKit.Swift", "1.5.3") \
           == "pkg:github/horizontalsystems/EvmKit.Swift@1.5.3"

def test_spm_url_to_purl_non_github_fallback():
    purl = spm_purl_from_url("https://example.com/foo.git", "1.0.0")
    assert purl.startswith("pkg:generic/spm-package?vcs_url=")
    assert "%3A%2F%2Fexample.com%2Ffoo.git" in purl
    assert purl.endswith("@1.0.0")
```

### Impl

`extractors/dependency_surface/purl.py`:

- `build_purl(ecosystem: Ecosystem, name: str, version: str, **extras) -> str`.
- `spm_purl_from_url(url: str, version: str) -> str` per spec §6.
- Maven: split `name` on `:` to get `(group, artifact)`.
- All inputs URL-encoded as needed; canonical lowercase host (per purl-spec).

### Commit

`feat(GIM-191): purl construction helpers (PyPI, Maven, SPM-GitHub, generic fallback)`

### Acceptance

`uv run pytest tests/extractors/unit/test_dependency_surface_purl.py -v` → all green;
`uv run pytest --cov=palace_mcp.extractors.dependency_surface.purl --cov-fail-under=90 ...` → green.

---

## Task 3: SPM parser

### Test (write first)

`tests/extractors/unit/test_dependency_surface_parser_spm.py`:

```python
def test_spm_parser_package_swift_only(tmp_path):
    (tmp_path / "Package.swift").write_text(textwrap.dedent('''
        // swift-tools-version: 5.9
        import PackageDescription
        let package = Package(
            name: "X",
            dependencies: [
                .package(url: "https://github.com/horizontalsystems/EvmKit.Swift.git", from: "1.5.0"),
                .package(url: "https://github.com/apple/swift-collections", exact: "1.1.4"),
            ],
            targets: [.target(name: "X")]
        )
    '''))
    # No Package.resolved → resolved_version="unresolved" for both
    r = parse_spm(tmp_path, project_id="project/x")
    assert {d.purl.split("@")[0] for d in r.deps} == {
        "pkg:github/horizontalsystems/EvmKit.Swift",
        "pkg:github/apple/swift-collections",
    }
    assert all(d.resolved_version == "unresolved" for d in r.deps)
    assert any("Package.resolved missing" in w for w in r.parser_warnings)

def test_spm_parser_with_resolved_v3(tmp_path):
    # Package.swift + Package.resolved v3 → resolved_version pinned
    ...
    r = parse_spm(tmp_path, project_id="project/x")
    assert {d.resolved_version for d in r.deps} == {"1.5.3", "1.1.4"}
    assert r.parser_warnings == ()

def test_spm_parser_with_resolved_v2_object_pins(tmp_path):
    # Older v2 schema: pins under "object.pins" rather than top-level
    ...

def test_spm_parser_branch_pin_unresolved(tmp_path):
    # Package.swift declares .package(url:..., branch:"main")
    # Package.resolved has revision but no version → resolved_version="unresolved"
    ...

def test_spm_parser_no_package_swift(tmp_path):
    r = parse_spm(tmp_path, project_id="project/x")
    assert r.deps == ()
    assert "Package.swift not found" in r.parser_warnings[0]
```

### Impl

`extractors/dependency_surface/parsers/spm.py`:

1. Read `Package.swift` text. Match `.package\(\s*url:\s*"(?P<url>[^"]+)"\s*,\s*(?P<kind>from|exact|branch|revision)?\s*:?\s*"(?P<ver>[^"]+)"\s*\)` (multi-line capable; use `re.MULTILINE | re.DOTALL` carefully).
2. Read `Package.resolved` if present. Try `data["pins"]` (v3) → fall back to `data["object"]["pins"]` (v2).
3. Match by `location` field (case-insensitive on github URL forms; strip `.git`).
4. For each declared, resolve version from `state.version` if present; else `state.revision[:7]` with warning; else `"unresolved"`.
5. Construct purl via `spm_purl_from_url(url, version)`.

### Commit

`feat(GIM-191): SPM parser (Package.swift + Package.resolved v2/v3)`

### Acceptance

All `test_dependency_surface_parser_spm` parametrized cases green.

---

## Task 4: Gradle parser

### Test (write first)

`tests/extractors/unit/test_dependency_surface_parser_gradle.py`:

```python
def test_gradle_parser_libs_versions_and_implementation(tmp_path):
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(textwrap.dedent('''
        [versions]
        appcompat = "1.7.1"
        retrofit = "3.0.0"

        [libraries]
        androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
        retrofit2 = { group = "com.squareup.retrofit2", name = "retrofit", version.ref = "retrofit" }
    '''))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(textwrap.dedent('''
        dependencies {
            implementation(libs.androidx.appcompat)
            testImplementation(libs.retrofit2)
        }
    '''))
    r = parse_gradle(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}
    assert "pkg:maven/androidx.appcompat/appcompat@1.7.1" in by_purl
    assert by_purl["pkg:maven/androidx.appcompat/appcompat@1.7.1"].scope == "compile"
    assert "pkg:maven/com.squareup.retrofit2/retrofit@3.0.0" in by_purl
    assert by_purl["pkg:maven/com.squareup.retrofit2/retrofit@3.0.0"].scope == "test"

def test_gradle_parser_alias_dot_variations(tmp_path):
    # libs.androidx.appcompat OR libs.androidxAppcompat OR libs.androidx-appcompat
    # all should resolve to the same library entry per Gradle's normalization rules.
    ...

def test_gradle_parser_unknown_alias_warns(tmp_path):
    # implementation(libs.does.not.exist) → parser_warning, NOT crash
    ...

def test_gradle_parser_multi_module(tmp_path):
    # Two build.gradle.kts files (app/ and core/); each declares the same dep
    # → 2 ParsedDep entries with different declared_in paths.
    ...

def test_gradle_parser_no_libs_versions_toml(tmp_path):
    # build.gradle.kts present but libs.versions.toml absent → parser warning, deps=()
    ...
```

### Impl

`extractors/dependency_surface/parsers/gradle.py`:

1. Read `gradle/libs.versions.toml` via `tomllib`.
2. Build alias map: walk `[libraries]`; for each entry resolve `version.ref` against `[versions]`.
   Normalize alias: `androidx-appcompat` → both `androidx.appcompat` and `androidx-appcompat` and `androidxAppcompat` (Gradle's `libs.X.Y` accessor pattern).
3. Find all `build.gradle.kts` files via `Path.rglob("build.gradle.kts")`.
4. For each, regex-match `(?P<scope>implementation|api|kapt|annotationProcessor|testImplementation|compileOnly|runtimeOnly)\s*\(\s*libs\.(?P<alias>[\w.\-]+)\s*\)`.
5. Resolve alias → emit `ParsedDep`. scope mapping: `implementation`/`api` → `"compile"`, `testImplementation` → `"test"`, `kapt`/`annotationProcessor` → `"build"`, `runtimeOnly` → `"runtime"`.
6. Emit warning for any unresolved alias.

### Commit

`feat(GIM-191): Gradle parser (libs.versions.toml + per-module build.gradle.kts)`

### Acceptance

All `test_dependency_surface_parser_gradle` parametrized cases green.

---

## Task 5: Python parser

### Test (write first)

`tests/extractors/unit/test_dependency_surface_parser_python.py`:

```python
def test_python_parser_pyproject_and_uv_lock(tmp_path):
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent('''
        [project]
        name = "x"
        dependencies = ["neo4j>=5.0", "graphiti-core==0.28.2"]
        [project.optional-dependencies]
        test = ["pytest>=7.0"]
    '''))
    (tmp_path / "uv.lock").write_text(textwrap.dedent('''
        version = 1
        [[package]]
        name = "neo4j"
        version = "5.28.2"

        [[package]]
        name = "graphiti-core"
        version = "0.28.2"

        [[package]]
        name = "pytest"
        version = "8.3.4"
    '''))
    r = parse_python(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}
    assert "pkg:pypi/neo4j@5.28.2" in by_purl
    assert by_purl["pkg:pypi/neo4j@5.28.2"].scope == "compile"
    assert "pkg:pypi/graphiti-core@0.28.2" in by_purl
    assert "pkg:pypi/pytest@8.3.4" in by_purl
    assert by_purl["pkg:pypi/pytest@8.3.4"].scope == "test"

def test_python_parser_no_uv_lock_unresolved(tmp_path):
    # pyproject only → resolved_version="unresolved" + warning
    ...

def test_python_parser_dependency_not_in_lock_warns(tmp_path):
    # pyproject says foo>=1.0; uv.lock has no "foo" → resolved="unresolved" + warning
    ...

def test_python_parser_no_pyproject(tmp_path):
    # absent → deps=(), warning
    ...
```

### Impl

`extractors/dependency_surface/parsers/python.py`:

1. Read `pyproject.toml` via `tomllib`.
2. From `[project.dependencies]` (PEP 621 list of strings) parse each via `packaging.requirements.Requirement` — get `req.name` + `req.specifier`.
3. From `[project.optional-dependencies]` for each group → scope mapping (test/build/dev → "test" / "build").
4. Read `uv.lock` via `tomllib`. Walk `[[package]]` array → build map `{name: version}`.
5. For each declared dep: `resolved_version = lock_map.get(name, "unresolved")` (warn on miss).
6. purl: `build_purl("pypi", req.name, resolved_version)`.

### Commit

`feat(GIM-191): Python parser (pyproject.toml + uv.lock)`

### Acceptance

All `test_dependency_surface_parser_python` parametrized cases green.

---

## Task 6: Neo4j writer

### Test (write first)

`tests/extractors/unit/test_dependency_surface_neo4j_writer.py` (mock driver):

```python
async def test_writer_merges_external_dependency(mock_driver):
    deps = [ParsedDep(project_id="project/x", purl="pkg:pypi/neo4j@5.28.2", ...)]
    n, e = await write_to_neo4j(mock_driver, deps, project_slug="x", group_id="project/x")
    # Verify Cypher MERGE called with correct params
    assert n == 1 and e == 1

async def test_writer_skips_existing_node_idempotent(mock_driver):
    # Second call with same dep → still 1 node (MERGE), 1 edge (MERGE on key)
    ...

async def test_writer_handles_unresolved_version(mock_driver):
    deps = [ParsedDep(..., resolved_version="unresolved")]
    n, e = await write_to_neo4j(mock_driver, deps, ...)
    # purl includes "@unresolved" or trailing-empty; node still merges idempotently
    assert n == 1
```

### Impl

`extractors/dependency_surface/neo4j_writer.py`:

```python
_UPSERT_EXT_DEP = """
MERGE (d:ExternalDependency {purl: $purl})
ON CREATE SET d.ecosystem = $ecosystem,
              d.resolved_version = $resolved_version,
              d.group_id = $group_id,
              d.first_seen_at = datetime()
ON MATCH  SET d.last_seen_at = datetime()
"""

_UPSERT_DEPENDS_ON_EDGE = """
MATCH (p:Project {slug: $project_slug})
MATCH (d:ExternalDependency {purl: $purl})
MERGE (p)-[r:DEPENDS_ON {scope: $scope, declared_in: $declared_in}]->(d)
ON CREATE SET r.declared_version_constraint = $declared_version_constraint,
              r.first_seen_at = datetime()
ON MATCH  SET r.declared_version_constraint = $declared_version_constraint,
              r.last_seen_at = datetime()
"""

async def write_to_neo4j(driver, deps, *, project_slug, group_id) -> tuple[int, int]:
    nodes_written = 0
    edges_written = 0
    async with driver.session() as session:
        for dep in deps:
            await session.run(_UPSERT_EXT_DEP, purl=dep.purl, ecosystem=dep.ecosystem,
                              resolved_version=dep.resolved_version, group_id=group_id)
            nodes_written += 1
            await session.run(_UPSERT_DEPENDS_ON_EDGE, project_slug=project_slug,
                              purl=dep.purl, scope=dep.scope, declared_in=dep.declared_in,
                              declared_version_constraint=dep.declared_version_constraint)
            edges_written += 1
    return nodes_written, edges_written
```

Note: `nodes_written` counts MERGE-attempted, NOT created. Real created-vs-matched accounting via Neo4j summary counters is a refinement (F). For v1 we report attempts.

### Commit

`feat(GIM-191): Neo4j writer (MERGE :ExternalDependency + :DEPENDS_ON edge)`

### Acceptance

All `test_dependency_surface_neo4j_writer` cases green.

---

## Task 7: Schema extension

### Test (write first)

`tests/extractors/unit/test_dependency_surface_schema_bootstrap.py`:

```python
async def test_schema_bootstrap_idempotent(neo4j_driver):
    await ensure_custom_schema(neo4j_driver)
    await ensure_custom_schema(neo4j_driver)  # second call must not raise
    # SHOW INDEXES and verify dep_surface index present

async def test_schema_includes_project_dep_lookup_index(neo4j_driver):
    await ensure_custom_schema(neo4j_driver)
    rows = await driver.execute_query("SHOW INDEXES YIELD name").records
    names = {r["name"] for r in rows}
    assert "dep_project_lookup" in names  # index for Project.slug→DEPENDS_ON traversal
```

### Impl

`extractors/foundation/schema.py` — append to `EXPECTED_SCHEMA.indexes`:

```python
IndexSpec(
    name="dep_project_lookup",
    label="Project",
    properties=("slug",),
),
```

(Note: if a `Project.slug` index already exists, this is a no-op idempotent. Verify via `SHOW INDEXES`.)

### Commit

`feat(GIM-191): schema extension — Project.slug index for dependency-surface queries`

### Acceptance

`test_dependency_surface_schema_bootstrap` green; existing `test_schema_drift` still green.

---

## Task 8: Extractor orchestrator

### Test (write first)

`tests/extractors/unit/test_dependency_surface_extractor.py`:

```python
async def test_extractor_no_manifests_returns_zero():
    extractor = DependencySurfaceExtractor()
    ctx = make_test_ctx(repo_path=tmp_path)  # empty repo
    stats = await extractor.run(graphiti=mock_graphiti, ctx=ctx)
    assert stats == ExtractorStats(nodes_written=0, edges_written=0)
    assert any(r.event == "dep_surface_no_manifests" for r in caplog.records)

async def test_extractor_python_only(tmp_path):
    # Setup pyproject.toml + uv.lock with 2 deps
    ...
    stats = await extractor.run(...)
    assert stats.nodes_written == 2
    assert stats.edges_written == 2
    # Assert dep_surface_complete event fires with ecosystems_present=["pypi"]

async def test_extractor_all_three_ecosystems(tmp_path):
    # SPM + Gradle + Python all present
    ...
    stats = await extractor.run(...)
    assert stats.nodes_written == 6
    assert stats.edges_written == 6

async def test_extractor_partial_failure_continues(tmp_path):
    # Gradle parser raises, SPM + Python succeed → emit dep_surface_failed for gradle,
    # dep_surface_complete still fires with ecosystems_present excluding gradle
    ...
```

### Impl

`extractors/dependency_surface/extractor.py` per spec §5.1.

- Deferred import for `get_driver`.
- Pre-flight: `_get_previous_error_code` + `check_resume_budget` + `ensure_custom_schema`.
- Auto-detect via `Path.is_file()` / `rglob`.
- Per-ecosystem try/except — failure of one parser does not block others. Emit `dep_surface_failed` JSONL event with ecosystem name + `error_repr`.
- Final summary `dep_surface_complete` event with all counts + ecosystems list.

### Commit

`feat(GIM-191): DependencySurfaceExtractor orchestrator + JSONL events`

### Acceptance

All `test_dependency_surface_extractor` cases green;
`uv run pytest --cov=palace_mcp.extractors.dependency_surface.extractor --cov-fail-under=90 ...` green.

---

## Task 9: Registry registration

### Test

`tests/extractors/unit/test_registry.py` (extend existing):

```python
def test_registry_includes_dependency_surface():
    from palace_mcp.extractors import registry
    assert "dependency_surface" in registry.EXTRACTORS
    assert registry.EXTRACTORS["dependency_surface"].name == "dependency_surface"
```

### Impl

`extractors/registry.py`:

```python
from palace_mcp.extractors.dependency_surface.extractor import DependencySurfaceExtractor
EXTRACTORS["dependency_surface"] = DependencySurfaceExtractor()
```

### Commit

`feat(GIM-191): register dependency_surface extractor`

### Acceptance

`test_registry_includes_dependency_surface` green.

---

## Task 10: Mini-fixture

### Impl

`tests/extractors/fixtures/dependency-surface-mini-project/`:

```
REGEN.md
Package.swift              — 2 SPM deps (one GitHub, one non-GitHub via vcs URL)
Package.resolved           — schema v3 with pins for both
gradle/libs.versions.toml  — 2 entries
app/build.gradle.kts       — 2 implementation() declarations
pyproject.toml             — 2 deps under [project.dependencies] + 1 under [project.optional-dependencies.test]
uv.lock                    — minimal lock with 3 packages
```

`REGEN.md` documents how to add a new ecosystem dep to the fixture (including the Package.resolved pin add).

### Commit

`test(GIM-191): mini-fixture covering SPM + Gradle + Python ecosystems`

### Acceptance

Fixture committed; tests in tasks 3-5 reference it where useful.

---

## Task 11: Integration test (real Neo4j via testcontainers)

### Test

`tests/extractors/integration/test_dependency_surface_integration.py`:

```python
@pytest.mark.integration
async def test_full_flow_against_fixture(neo4j_container):
    # 1. Spin testcontainer Neo4j; await driver
    # 2. Set repo_path = fixtures/dependency-surface-mini-project
    # 3. Register :Project {slug: "fixture-mini"}
    # 4. Call extractor.run()
    # 5. Cypher: count :ExternalDependency → expect 6 (2 SPM + 2 Gradle + 2 Python)
    # 6. Cypher: count :DEPENDS_ON → expect 6 (one per ParsedDep, declared_in distinct)

@pytest.mark.integration
async def test_cross_project_dedup(neo4j_container):
    # Two synthetic projects both depending on neo4j@5.28.2 (Python)
    # → SINGLE :ExternalDependency node, TWO :DEPENDS_ON edges from different :Project nodes

@pytest.mark.integration
async def test_idempotent_remerge(neo4j_container):
    # Run extractor twice on same project → same node + edge counts after each run
```

### Impl

Standard testcontainers Neo4j fixture (reuse pattern from
`tests/extractors/integration/test_symbol_index_python_integration.py`).

### Commit

`test(GIM-191): integration tests (testcontainers Neo4j) — flow + dedup + idempotency`

### Acceptance

`uv run pytest tests/extractors/integration/test_dependency_surface_integration.py -m integration -v`
green. Integration MUST be in `tests/integration/` pytest scope (per
GIM-188 tightening; CR Phase 3.1 will check).

---

## Task 12: Smoke script + runbook + CLAUDE.md

### Impl

1. `services/palace-mcp/scripts/smoke_dependency_surface.py` — per spec §9.4.2.
2. `docs/runbooks/dependency-surface.md` — sections: setup (no env vars needed), full ingest example for gimle / uw-android, Cypher query examples, troubleshooting (parser warnings interpretation, missing manifest cases, cross-project dedup verification).
3. `CLAUDE.md` §"Extractors":
   - Add `dependency_surface` to "Registered extractors" list.
   - Add a "Operator workflow: Dependency surface" section similar to other extractors.

### Commit

`docs(GIM-191): smoke script + runbook + CLAUDE.md update`

### Acceptance

Files present; manual review by self-check; will be re-checked in Phase 3.1.

---

## Task 13: Final gate + handoff to CR

Run all of:

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

All must exit 0. Paste output verbatim in CR Phase 3.1 handoff comment.

Then atomic-handoff to `[@CodeReviewer](agent://bd2d7e20-7ed8-474c-91fc-353d610f4c52?i=eye)` per `phase-handoff.md` (PATCH `status + assigneeAgentId + comment` in one call, then GET-verify; on mismatch retry once + escalate Board per GIM-188 rule).

### Commit

(no code commit — handoff comment only)

---

## Phase 3.1 — CR Mechanical Review

CR's compliance checklist must include (per `compliance-enforcement.md`):

- [ ] Scope audit: `git diff --name-only origin/develop...HEAD | sort -u` matches §4 file list verbatim.
- [ ] `tests/integration/` IS in pytest scope (per GIM-188 tightening — aggregate counts excluding it do not satisfy CRITICAL test-additions).
- [ ] Per-module 90% coverage for extractor + purl + parsers.
- [ ] All JSONL events from spec §5.3 covered by ≥1 test each.
- [ ] purl construction parametrized test covers all 5 ecosystem cases from §6 table.
- [ ] No `if isError:` tautological assertion patterns in any test.

If any blocker → REQUEST CHANGES with formal `[@implementer](agent://...?i=...)` mention and `status=blocked` per phase-handoff retry/escalate rule.

---

## Phase 3.2 — Opus Adversarial Review

Required vectors (per spec §12 step 5):

- purl collisions across projects (verify dedup invariant in §3.4).
- Gradle KTS regex coverage on weird syntactic variants (e.g. `add("implementation", libs.X)`, `dependencies.implementation(libs.X)`).
- `uv.lock` schema drift: what if uv 2.x changes the TOML shape?
- Concurrent ingest of two projects with overlapping deps (race on MERGE — palace-mcp event loop serializes MCP tool calls, so this is N/A unless someone manually runs in parallel; document).
- Edge MERGE semantics: same `(project, dep, scope)` but different `declared_in` path → separate edges (intentional? operator's call).

---

## Phase 4.1 — QA Live Smoke (iMac)

QA executes per spec §9.4 on iMac via SSH. Mandatory smoke gate criteria
listed in §9.4.4. Evidence comment authored by **QAEngineer** (per
phase-handoff `Pre-close checklist`).

---

## Phase 4.2 — CTO merge

Squash-merge to develop after CI green. Submodule fragments (if any new
edits) follow standard FB+PR flow.

---

## Self-review summary

This plan covers spec §2 IN items end-to-end. 13 tasks; each ends with a
green test target. No silent scope reduction (per
`feedback_silent_scope_reduction.md`): every task lists its expected file
deliverables, and Phase 3.1 will diff-audit against §4 file list.

Estimated implementation effort: 1.5-2 days for a single Claude
implementer (PythonEngineer) following TDD strictly. Total LOC: ~890 prod
+ ~970 test + ~400 docs/fixture/runbook. Smaller than GIM-186 (~3100 LOC)
because no Tantivy, no GitHub API client, no checkpoint state.
