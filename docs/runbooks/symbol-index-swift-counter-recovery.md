# Symbol Index Counter Recovery

`symbol_index_swift` and the other symbol-index extractors persist an in-degree
counter at `/var/lib/palace/tantivy/in_degree_counter.json`.

## Default behavior

On startup, the extractor now self-heals stale or corrupt counter state:

- If the counter JSON is corrupt, unreadable, wrong-version, or tied to an old
  `run_id`, the extractor logs a warning, deletes the stale file, and starts
  with a fresh counter.
- The next successful run rewrites `in_degree_counter.json` with the current
  `run_id`.

## Forced reset

Set `PALACE_COUNTER_RESET=1` before starting `palace-mcp` to force a clean
counter on the next run:

```bash
PALACE_COUNTER_RESET=1 docker compose --profile review up -d --force-recreate palace-mcp
```

With the flag set, extractor startup deletes `in_degree_counter.json` before it
is read and rebuilds it from the current ingest.

## When Manual Intervention Is Still Required

Manual cleanup is only needed if the process cannot delete the counter file at
startup, for example because of a permissions or volume-mount problem. In that
case the extractor returns `counter_state_corrupt` with the file path in the
error context.
