# Hostile fixtures

- Date: `2026-05-06`

## Cases

- `env-leak`: PASS
- `hanging-config`: PASS
- `timeout`: PASS
- `wrapper-download`: PASS — refused with host_gradle_wrapper_forbidden before exec
- `absolute-path`: PASS
- `bazel-cmdline-leak`: PASS
- `cancellation-cleanup`: PASS
- `unbounded-output`: PASS — stdout truncated at 16384 bytes and process killed on output bound

## Interpretation

A `PASS` means the spike helper either sanitized the sensitive field, timed out and killed the process group, or blocked the unsafe wrapper path before execution.
