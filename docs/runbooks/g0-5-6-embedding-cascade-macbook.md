# G0.5.6 Embedding Cascade on MacBook

Goal: run the post-`GIM-816` embedding cascade on Apple Silicon and persist the
results into the iMac Neo4j without launching the full embedding pass on the
Intel iMac.

## Assumptions

- Execute from `develop` at or after `3a83b3ab` (`symbol_embedding_idx` present
  in schema and semantic search wired to it).
- Use a MacBook runtime with the local Qodo model cache available.
- Point the MacBook `palace-mcp` runtime at the iMac Neo4j.
- Keep `PALACE_EMBEDDING_LIMIT` unset for the real cascade. A bounded limit is
  only valid for smoke, not for G0.5.6 acceptance.

## Preflight

Confirm the vector index exists and is online before the first project:

```cypher
SHOW VECTOR INDEXES
YIELD name, state, labelsOrTypes, properties
WHERE name = 'symbol_embedding_idx'
RETURN name, state, labelsOrTypes, properties;
```

Confirm `palace-mcp` is healthy on the MacBook runtime before and after the
cascade:

```bash
curl -fsS http://localhost:8080/healthz
```

## Swift Kit Cascade

`ingest_swift_kit.sh` defaults to the full Swift-kit audit order, so pass the
G0.5.6 extractor override explicitly.

```bash
for slug in bitcoin-core evm-kit bitcoin-kit dash-kit; do
  bash paperclips/scripts/ingest_swift_kit.sh "$slug" \
    --extractors symbol_index_swift,dead_code,embedding_symbol
done
```

## Xcode App Cascade

`ingest_xcode_app.sh` does not include `embedding_symbol` in its default
extractor set, so the override is required here too.

```bash
bash paperclips/scripts/ingest_xcode_app.sh \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --workspace Wallet.xcworkspace \
  --slug uw-ios-app \
  --bundle uw-ios \
  --extractors symbol_index_swift,dead_code,embedding_symbol
```

## Verification Queries

For each slug in `bitcoin-core`, `evm-kit`, `bitcoin-kit`, `dash-kit`,
`uw-ios-app`, capture the latest run evidence for the three required
extractors:

```cypher
MATCH (r:IngestRun {project: $slug})
WHERE r.extractor_name IN ['symbol_index_swift', 'dead_code', 'embedding_symbol']
WITH r.extractor_name AS extractor, max(r.started_at) AS started_at
MATCH (latest:IngestRun {project: $slug, extractor_name: extractor, started_at: started_at})
RETURN extractor, latest.success AS success, latest.error_code AS error_code, latest.started_at AS started_at
ORDER BY extractor;
```

Then capture the roadmap acceptance count:

```cypher
MATCH (s:Symbol {group_id: $group_id})
WHERE s.embedding IS NOT NULL
RETURN count(s) AS embedding_count;
```

Use `group_id = 'project/<slug>'`.

Acceptance target:

- Normal project: `embedding_count > 100`
- Small kit exception: `10 <= embedding_count <= 100`, but only if the issue
  comment records the exact count and why the kit is legitimately small

## Issue Comment Checklist

Post one evidence block per project with:

- extractor results for `symbol_index_swift`, `dead_code`, `embedding_symbol`
- `embedding_count`
- whether the count cleared `>100` or is a documented small-kit exception
- final `curl -fsS http://localhost:8080/healthz` result
