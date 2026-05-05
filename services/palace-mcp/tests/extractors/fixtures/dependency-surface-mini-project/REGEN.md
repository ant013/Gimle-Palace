# dependency-surface-mini-project — Fixture Guide

## Purpose

Static fixture covering all 3 supported ecosystems (SPM, Gradle, Python).
Used by integration tests in `test_dependency_surface_integration.py`.

## Expected dependency counts

| Ecosystem | Count | Notes |
|-----------|-------|-------|
| SPM (github) | 2 | EvmKit.Swift@1.5.3, swift-collections@1.1.4 — pinned in Package.resolved v3 |
| Gradle (maven) | 2 | androidx-appcompat@1.7.1 (compile), retrofit@3.0.0 (test) |
| Python (pypi) | 3 | neo4j@5.28.2 (compile), graphiti-core@0.28.2 (compile), pytest@8.3.4 (test) |
| **Total** | **7** | 7 nodes, 7 edges on first run |

## Adding a new SPM dependency

1. Add `.package(url: "...", from: "X.Y.Z")` to `Package.swift` `dependencies` array.
2. Add a matching pin to `Package.resolved` `pins` array (copy existing entry, update fields).
3. Update the "Expected dependency counts" table above.
4. Run `uv run pytest tests/extractors/integration/test_dependency_surface_integration.py -m integration -v` — update expected counts in test assertions if needed.

## Adding a new Gradle dependency

1. Add a version entry to `gradle/libs.versions.toml` under `[versions]`.
2. Add a library entry under `[libraries]`.
3. Add `implementation(libs.<alias>)` to `app/build.gradle.kts`.
4. Update counts and rerun tests.

## Adding a new Python dependency

1. Add to `pyproject.toml` `[project.dependencies]` or `[project.optional-dependencies]`.
2. Add a matching `[[package]]` entry to `uv.lock`.
3. Update counts and rerun tests.
