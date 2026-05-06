# Cross-Repo Version Skew Extractor — Runbook

## What it does

Detects when modules / bundle members pin different `resolved_version`s
of the same external library. Reads `:Project-[:DEPENDS_ON]->:ExternalDependency`
from `dependency_surface` (GIM-191). Single MCP tool: `palace.code.find_version_skew`.

## Trust assumptions

`find_version_skew` enumerates the supply-chain composition of any
registered project/bundle. In multi-tenant deployments treat output as
business-confidential. v1 single-tenant; ACL is a future palace-mcp slice.

## Running

Prereq: `dependency_surface` has run for the project (or every member
of the bundle).

```
palace.ingest.run_extractor(name="cross_repo_version_skew", project="<slug>")
# or
palace.ingest.run_extractor(name="cross_repo_version_skew", bundle="<name>")

palace.code.find_version_skew(bundle="<name>", min_severity="minor", top_n=20)
```

## Knobs

| Env | Default | Effect |
|-----|---------|--------|
| `PALACE_VERSION_SKEW_TOP_N_MAX` | 500 | Upper bound for `top_n` arg |
| `PALACE_VERSION_SKEW_QUERY_TIMEOUT_S` | 30 | Bolt aggregation timeout (s) |

## Severity ranks

| Severity | Rank | Meaning |
|----------|:----:|---------|
| `major` | 3 | semver major differs |
| `minor` | 2 | major equal, minor differs |
| `patch` | 1 | major+minor equal (incl. parse-equivalent strings) |
| `unknown` | 0 | one or both versions don't parse under PEP 440 |

`min_severity='major'` returns only rank-3 groups.
`min_severity='unknown'` includes all severities (rank ≥ 0).

## Drift detection (count-only, v1)

```
palace.memory.lookup(
    entity_type="IngestRun",
    filters={"extractor_name": "cross_repo_version_skew", "target_slug": "uw-ios"},
    limit=10,
)
```

Compare `skew_groups_total` between two `:IngestRun` snapshots.
Content-diff (which purls changed) is a future slice.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `dependency_surface_not_indexed` | GIM-191 hasn't run | run `palace.ingest.run_extractor(name='dependency_surface', project=...)` first |
| `bundle_has_no_members` | bundle exists but `add_to_bundle` was never called | call `palace.memory.add_to_bundle` |
| `bundle_not_registered` | bundle name has typo or was never created | call `palace.memory.register_bundle` first |
| `top_n_out_of_range` | passed top_n ≥ 10_000 | pass smaller top_n |
| Project-mode returns 0 skew on UW Android | by design — Gradle alias resolves to one version | use `bundle="uw-android"` (single-member) for forward compatibility |
| Warnings include `purl_malformed` | GIM-191 wrote a row whose `purl` lacks `pkg:` prefix | inspect the row, file a `dependency_surface` regression bug |

## Erasure

Not applicable — this extractor reads existing data, writes only audit
`:IngestRun` nodes. To remove an audit run:

```cypher
MATCH (r:IngestRun {run_id: $run_id, extractor_name: 'cross_repo_version_skew'})
DELETE r
```
