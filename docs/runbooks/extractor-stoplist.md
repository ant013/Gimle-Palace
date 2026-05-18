# Extractor Stop-List Runbook

**Source:** `services/palace-mcp/src/palace_mcp/extractors/foundation/walk.py`
**Issue:** GIM-348

## Overview

All palace-mcp extractors that walk repository source files use the shared
`walk_repo()` generator (or `should_skip_path()` predicate for pygit2-based walkers).
These helpers prune directories in the default stop-list before descent, preventing
timeouts caused by scanning build artifact / dependency subtrees.

## `DEFAULT_STOP_DIRS`

| Directory | Ecosystem | Rationale |
|---|---|---|
| `.build` | Swift / SPM | SPM build artifacts + fetched package checkouts (e.g. `.build/checkouts/GRDB.swift`). Primary cause of GIM-334 timeouts. |
| `.git` | All | VCS internals. pygit2 walkers already skip this; included for completeness. |
| `.gradle` | Java / Kotlin | Gradle build cache and configuration cache. |
| `.idea` | JetBrains IDEs | IDE project metadata. |
| `.kotlin` | Kotlin | Kotlin compiler daemon workspace. |
| `.mypy_cache` | Python | mypy type-checking cache. |
| `.pytest_cache` | Python | pytest result cache. |
| `.swiftpm` | Swift / SPM | SPM local package resolution directory. |
| `.tantivy` | palace-mcp internal | Tantivy search index written by palace-mcp itself. |
| `.venv` | Python | Python virtual environment. |
| `__MACOSX` | macOS | macOS metadata injected into ZIP archives. |
| `__pycache__` | Python | Python bytecode cache. |
| `build` | Java / Android / generic | Gradle, CMake, and generic build output. |
| `Carthage` | iOS / Swift | Carthage dependency checkouts and builds. |
| `DerivedData` | Xcode | Xcode build products and intermediate files. |
| `dist` | JS / Python | Distribution/wheel output. |
| `node_modules` | JS / TS | npm/yarn package tree (often millions of files). |
| `Pods` | iOS / Swift | CocoaPods dependency sources. |
| `SourcePackages` | Xcode / SPM | Xcode-managed SPM package checkouts. |
| `target` | Rust / Maven | Rust/Maven build output. |
| `vendor` | Go / PHP / generic | Vendored dependency copies. |

## `DEFAULT_STOP_PREFIXES`

| Prefix | Rationale |
|---|---|
| `.palace-xcb-` | palace-mcp transient xcbuild workspace directories. |
| `.palace-scip-` | palace-mcp transient SCIP index workspace directories. |

These are matched as *prefixes* on directory name components, allowing the unique
suffix (build hash) to vary between runs.

## Adding per-extractor custom excludes

Pass `extra_excludes` and/or `extra_prefixes` to `walk_repo()` or `should_skip_path()`:

```python
from palace_mcp.extractors.foundation.walk import walk_repo

for path in walk_repo(repo_root, extra_excludes=frozenset({"MyGeneratedDir"})):
    ...
```

Custom excludes are **additive** — the default stop-list always applies.

## Why `os.walk` pruning, not `rglob` post-filter

`Path.rglob()` descends into all directories before filtering. `os.walk` with
in-place `dirnames[:]` mutation prunes entire subtrees before descent. For a
repo like BitcoinCore.Swift where `.build/checkouts/` contains ~200K Swift LOC
of GRDB, Alamofire, and swift-nio-ssl, post-filter traversal caused 300-second
timeouts in `code_ownership`, `crypto_domain_model`, and `hotspot` (GIM-334).

## Affected extractors

| Extractor | Walk method | Change |
|---|---|---|
| `hotspot` | `walk_repo(root, suffixes=_LIZARD_EXTENSIONS)` | Replaced `rglob("*")` + post-filter |
| `code_ownership` | `should_skip_path(parts)` in pygit2 `visit()` | Added subtree skip |
| `crypto_domain_model` | `walk_repo(target, suffixes={".swift"})` | Replaced `rglob("*.swift")` |
| `error_handling_policy` | `walk_repo(repo_root, suffixes={".swift"})` | Replaced `rglob("*.swift")` + added `is_file()` guard |
