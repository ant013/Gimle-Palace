# uw-ios-bundle-mini-project — synthetic 3-Kit fixture (GIM-182)

This directory provides minimal synthetic SCIP indexes for bundle integration testing.

## Kit overview

| Kit slug      | Role              | Key symbols |
|---------------|-------------------|-------------|
| `uw-ios-app`  | user app (bundle-member slug; bundle slug is `uw-ios`) | uses `EvmKit.Address` |
| `EvmKit-mini` | first-party Kit   | defines `EvmKit.Address` |
| `Eip20Kit-mini` | first-party Kit | defines `Eip20Kit.Erc20Provider`, uses `EvmKit.Address` |

## Key invariants tested

1. `find_references(qualified_name="EvmKit.Address", project="uw-ios")` expands
   through the bundle and finds usages in `uw-ios-app` AND `Eip20Kit-mini`.
2. `uw-ios-app` slug (the app project) is distinct from `uw-ios` (the bundle slug).
   Querying `project="uw-ios-app"` sees only that project's own index.
3. `register_bundle("uw-ios")` succeeds after all 3 members are registered.

## SCIP files

SCIP fixtures are generated at test time using `scip_factory.build_swift_scip_index()`
and written to `tmp_path` — no committed binary blobs.
The `scip/` subdirectories here are intentionally absent; integration tests use
`tmp_path` and `PALACE_SCIP_INDEX_PATHS` env overrides.

## GIM-128 scope note

Fixture paths here are under `uw-ios-bundle-mini-project/` and do not overlap
with `uw-android-mini-project/`, `jvm-mini-project/`, or other GIM-128 fixtures.
