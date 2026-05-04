# Dependency Surface Extractor — Runbook

## Overview

The `dependency_surface` extractor parses declared + resolved dependencies from
SPM, Gradle, and Python manifests in a mounted repo and writes
`:ExternalDependency` nodes + `:DEPENDS_ON` edges to Neo4j.

**Supported ecosystems (v1):**
- SPM: `Package.swift` + `Package.resolved` (v2 and v3)
- Gradle: `gradle/libs.versions.toml` + per-module `build.gradle.kts`
- Python: `pyproject.toml` (PEP 621) + `uv.lock`

**No env vars required** — the extractor reads files from the mounted repo path.
GitHub token (`PALACE_GITHUB_TOKEN`) is not needed.

---

## Setup

Prerequisites:
1. `palace-mcp` container running (`docker compose --profile review up -d`)
2. Target repo mounted at `/repos/<slug>` (see `CLAUDE.md §Mounting project repos`)

No additional env vars needed for the extractor itself.

---

## Running the extractor

### Via MCP tool

```
palace.ingest.run_extractor(name="dependency_surface", project="gimle")
```

Example success response:
```json
{
  "ok": true,
  "run_id": "...",
  "extractor": "dependency_surface",
  "project": "gimle",
  "duration_ms": 42,
  "nodes_written": 7,
  "edges_written": 7,
  "success": true
}
```

### Via smoke script (on iMac)

```bash
ssh iMac
cd /Users/Shared/Ios/Gimle-Palace/services/palace-mcp
uv run python scripts/smoke_dependency_surface.py --project gimle --repo-path /Users/Shared/Ios/Gimle-Palace
```

For uw-android:
```bash
uv run python scripts/smoke_dependency_surface.py --project uw-android --repo-path /Users/Shared/Android/unstoppable-wallet-android
```

---

## Example: full ingest for gimle (Python project)

```bash
# 1. Run extractor
palace.ingest.run_extractor(name="dependency_surface", project="gimle")

# 2. Query results
MATCH (p:Project {slug: "gimle"})-[r:DEPENDS_ON]->(d:ExternalDependency)
RETURN d.purl, r.scope, r.declared_in
ORDER BY d.purl
```

Expected: all deps from `services/palace-mcp/pyproject.toml` + `uv.lock`.

## Example: full ingest for uw-android (Gradle project)

```bash
# 1. Ensure repo mounted at /repos/uw-android
# 2. Run extractor
palace.ingest.run_extractor(name="dependency_surface", project="uw-android")

# 3. Query results
MATCH (p:Project {slug: "uw-android"})-[r:DEPENDS_ON]->(d:ExternalDependency)
RETURN d.ecosystem, count(d) AS cnt
```

---

## Cypher query examples

### All deps for a project
```cypher
MATCH (p:Project {slug: "gimle"})-[r:DEPENDS_ON]->(d:ExternalDependency)
RETURN d.purl, r.scope, r.declared_in, d.resolved_version
ORDER BY r.scope, d.purl
```

### Cross-project dedup — same purl across projects
```cypher
MATCH (d:ExternalDependency)<-[:DEPENDS_ON]-(p:Project)
WITH d, collect(p.slug) AS projects
WHERE size(projects) > 1
RETURN d.purl, projects
ORDER BY d.purl
```

### Unresolved deps (no lock file pin)
```cypher
MATCH (p:Project)-[:DEPENDS_ON]->(d:ExternalDependency {resolved_version: "unresolved"})
RETURN p.slug, d.purl, d.ecosystem
```

### Dependency count by ecosystem
```cypher
MATCH ()-[:DEPENDS_ON]->(d:ExternalDependency)
RETURN d.ecosystem, count(d) AS cnt
ORDER BY cnt DESC
```

---

## Troubleshooting

### `dep_surface_no_manifests` in logs

The extractor found no manifest files in the repo path.

Check:
1. Is the repo mounted? `docker exec palace-mcp-palace-mcp-1 ls /repos/<slug>`
2. Does the repo have `Package.swift`, `gradle/libs.versions.toml`, or `pyproject.toml`?
3. Does the `Project.slug` match the mounted path slug?

### `dep_surface_gradle_warning: libs.versions.toml not found`

The repo has `build.gradle.kts` files but no `gradle/libs.versions.toml`.
Common in older Gradle projects that use direct version declarations.
**This is a warning, not an error** — Python and SPM deps still parse.

### `dep_surface_python_warning: 'foo' not found in uv.lock`

A package in `pyproject.toml` has no pin in `uv.lock`.
`resolved_version` will be `"unresolved"` for that dep.
Run `uv lock` in the project to refresh the lock file.

### Missing `:Project` node error

The writer uses `MATCH (p:Project {slug: $slug})` to create edges.
If no `:Project` node exists for the slug, edges are silently no-op'd
(MERGE finds nothing to match). Create it manually:

```cypher
MERGE (p:Project {slug: "my-slug", group_id: "project/my-slug"})
```

Or run `palace.memory.register_project("my-slug")` if available.

### Cross-project dedup verification

After running for 2 projects, verify shared nodes:
```cypher
MATCH (d:ExternalDependency)<-[:DEPENDS_ON]-(p:Project)
WITH d, collect(p.slug) AS projects
WHERE size(projects) > 1
RETURN count(d) AS shared_dep_count
```

Non-zero = dedup is working correctly.

---

## Architecture notes

- **Single-phase**: parses all manifests in one pass; no Tantivy, no checkpoint.
- **Idempotent**: MERGE on `purl` (node) + `(scope, declared_in)` (edge). Re-run on unchanged manifests → `nodes_written=0, edges_written=0`.
- **First-writer-wins**: `resolved_version` on `:ExternalDependency` set on first write only. If two projects declare the same dep with different versions, whichever runs first wins the node; both get `:DEPENDS_ON` edges.
- **Per-ecosystem isolation**: if one parser fails (e.g., malformed TOML), others continue. Check logs for `dep_surface_failed ecosystem=...`.
