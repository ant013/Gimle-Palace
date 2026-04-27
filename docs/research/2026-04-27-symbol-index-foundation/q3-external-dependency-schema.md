# Q3 — Unified `:ExternalDependency` schema (voltagent independent track)

Date: 2026-04-27
Track: Board cross-check (parallel to ResearchAgent autonomous track on GIM-100)

## Executive recommendation

**Use PURL (Package URL, ECMA-427 December 2025) as universal canonical key.** Single `:ExternalDependency` label + `ecosystem` property discriminator. Version constraint on edge, resolved version on node.

## Schema (recommended)

### `:ExternalDependency` node

| Property | Type | Notes |
|---|---|---|
| `purl` | String UNIQUE | Package URL per ECMA-427: `pkg:<type>/<namespace>/<name>@<version>` |
| `ecosystem` | String INDEXED | npm \| cargo \| pypi \| maven \| cocoapods \| swift \| gem \| generic \| github |
| `canonical_name` | String INDEXED | Normalized per-ecosystem (PEP 503 for pypi, lowercase for npm, etc.) |
| `resolved_version` | String NULLABLE | From lockfile; commit SHA for git deps; NULL if manifest-only |
| `source_type` | String | registry \| git \| path \| vendor \| binary |
| `registry_url` | String NULLABLE | Default implied by ecosystem unless overridden (private Nexus etc.) |
| `integrity_hash` | String NULLABLE | SHA-512 SRI (npm), SHA-256 (cargo/uv/soldeer), SHA-1 (cocoapods spec) |
| `git_url` | String NULLABLE | For source_type=git |
| `git_ref` | String NULLABLE | For source_type=git: tag/branch/SHA |
| `license` | String NULLABLE | SPDX expression (enrichment phase) |
| `group_id` | String | Graphiti namespace scoping |
| `first_seen_at`, `last_seen_at`, `extractor_source` | DateTime/String | Provenance |

### `[:USES]` edge

```
(:Project)-[:USES {
  version_constraint: String,    -- raw from manifest (`^1.2.3`, `~> 5.0`, `>=1.0,<2.0`)
  dep_scope: String,             -- prod | dev | optional | peer | build | test
  extras: [String] NULLABLE,     -- python extras, cargo features
  manifest_file: String,         -- "package.json", "Cargo.toml", etc.
  declared_at_commit: String NULLABLE,
}]->(:ExternalDependency)
```

### `[:DEPENDS_ON]` transitive edge

Only populated when extractor parsed full closure from lockfile (npm, cargo, uv, CocoaPods). Don't synthesize for git-submodule mode (no transitive metadata).

## Per-ecosystem coverage matrix

| Ecosystem | Manifest | Lockfile | PURL type | Notes |
|---|---|---|---|---|
| npm/pnpm/yarn | `package.json` | `package-lock.json`/`yarn.lock`/`pnpm-lock.yaml` | `pkg:npm/...` | Scope `@scope/name` percent-encoded |
| Cargo (Rust + Solana) | `Cargo.toml` | `Cargo.lock` v3 | `pkg:cargo/...` | Crate names globally unique, no namespace |
| Python (uv/pip) | `pyproject.toml` | `uv.lock`, `pylock.toml` (PEP 751) | `pkg:pypi/...` | PEP 503 canonical name normalization |
| CocoaPods | `Podfile` | `Podfile.lock` | `pkg:cocoapods/...` | Pod names globally unique on CDN |
| Swift Package Manager | `Package.swift` | `Package.resolved` v3 | `pkg:swift/owner/repo` | Identity = lowercased repo base |
| Carthage | `Cartfile` | `Cartfile.resolved` | `pkg:github/...` (no native PURL) | Maintenance mode 2023+ |
| Gradle (Kotlin/Android) | `build.gradle.kts` + `libs.versions.toml` | `gradle.lockfile` (opt-in!) | `pkg:maven/group/artifact` | BOM version indirection requires lockfile |
| Foundry/Solidity | `foundry.toml` + `remappings.txt` | `soldeer.lock` (Soldeer only) | `pkg:github/...` (submodule) / `pkg:generic` (Soldeer) | Default = git submodules, no lockfile |
| TON FunC/Tact | `package.json` (npm toolchain only) | npm lockfiles | `pkg:npm/...` (toolchain) / `pkg:generic` или `pkg:github` (contracts) | **No native package manager for contract deps** |

## Cross-extractor ownership

| Extractor | Role |
|---|---|
| **#5 Dependency Surface** (primary owner) | CREATE + MERGE all `:ExternalDependency` nodes; write `[:USES]` edges |
| **#25 Build System** | Enriches Gradle-specific (BOM membership, dep_scope details). MERGE on `purl`, never CREATE |
| **#39 Cross-Repo Version Skew** | Read-only — derives metrics, writes own `:AnalysisResult` nodes |
| **Registry Enrichment** (future) | Adds `license`, `description`, `homepage_url`, `version_published_at` |
| **Vulnerability Surface** (future) | `[:HAS_VULNERABILITY]` edges to `:CVE` nodes |

## Idempotency Cypher pattern

```cypher
MERGE (d:ExternalDependency {purl: $purl})
ON CREATE SET d.ecosystem=..., d.canonical_name=..., d.first_seen_at=datetime(), ...
ON MATCH SET d.last_seen_at=datetime(),
             d.integrity_hash=coalesce($integrity_hash, d.integrity_hash),
             d.resolved_version=coalesce($resolved_version, d.resolved_version)
```

`coalesce()` allows later extractors to fill NULLs without overwriting non-NULL values.

## 6 open gaps

1. **HIGH: TON FunC native package manager** — confirm via tact-lang/tact + ton-org/blueprint repos that no `blueprint.dependencies` or similar exists yet. As of research date 2026-04-27 — none found.
2. **MEDIUM: Soldeer lockfile format stability** — alpha/beta in 2024; minor versions renamed `sdependencies`→`dependencies`. Version-detect at parse time.
3. **MEDIUM: Gradle lockfile opt-in absent** — `gradle.lockfile` is opt-in; many real projects skip it. Handle `resolved_version=NULL` gracefully.
4. **LOW: CocoaPods + SPM coexistence** — same project may have both `Podfile.lock` AND `Package.resolved`. Different `manifest_file` values, no schema change needed.
5. **LOW: Cargo workspace member dedup** — multiple member `Cargo.toml` declare same crate with different (compatible) constraints; root `Cargo.lock` is single source of truth.
6. **LOW: Maven BOM indirection** — without lockfile, version is BOM-delegated. Mark `version_constraint = "bom:..."` for enrichment phase.

## Why not split resolved-version into separate node

A "resolved instance" pattern (`(:ManifestDep)-[:PINS]->(:ResolvedDep)`) adds query complexity without proportionate benefit. PURL encodes ecosystem+name+version, so each resolved version is naturally a distinct node. Satisfies version skew detection, freshness analysis, CVE mapping (CVE DBs key on `(ecosystem, name, version)` — exactly the PURL key).

## Confidence summary

- **HIGH** for Cargo, npm, pypi (PEP), CocoaPods, Gradle — official docs + lockfile spec primary sources
- **MEDIUM-HIGH** for SPM (no single official format spec page; relied on Swift evolution proposals)
- **MEDIUM** for Foundry/Soldeer — Soldeer format still evolving
- **MEDIUM** for TON — confirmed absence of package manager via official TON docs

## Top sources

- ECMA-427 Package URL spec (December 2025) — international standard
- github.com/package-url/purl-spec — primary reference
- doc.rust-lang.org/cargo/reference/specifying-dependencies.html
- packaging.python.org/en/latest/specifications/pylock-toml/ (PEP 751)
- guides.cocoapods.org/using/using-cocoapods.html
- docs.swift.org/package-manager/PackageDescription/
- docs.gradle.org/current/userguide/version_catalogs.html
- getfoundry.sh/guides/project-setup/soldeer/
- docs.ton.org/contract-dev/blueprint/overview
