# Bazel contract

- Date: `2026-05-06`

## Local status

Local `bazel` / `bazelisk` binary is not installed, so this artifact captures a committed contract sample plus the exact command boundary rather than a live run.

## Expected commands

```bash
bazel query 'deps(//app:wallet)'
bazel aquery --output=jsonproto 'deps(//app:wallet)'
```

## Validation

Schema: `contracts/bazel-query-aquery-v1.schema.json`

Sample: `contracts/bazel-query-aquery-v1.sample.json`

JSON Schema validation: `PASS`

Unknown action field check: `PASS — $.aquery.actions[0]: unexpected keys ['raw_command_line']`

The sample deliberately redacts raw action command lines and keeps only bounded input/output samples.

## Sources

- Official query docs: https://bazel.build/docs/query-how-to
- Official aquery docs: https://bazel.build/versions/7.3.0/query/aquery

## Recommendation impact

This leaves Bazel runtime behavior partially unproven on this machine. Production implementation should stay blocked until a real sandboxed Bazel capture is added.
