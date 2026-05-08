# Skip if unsandboxed proof

- Date: `2026-05-06`

## Structured skip

```json
{
  "ok": false,
  "skip_reason": "build_system_unsandboxed",
  "sandbox_available": true,
  "command_policy": "skip before tool invocation"
}
```

## Reasoning

Unsandboxed mode is treated as a structured skip before Gradle, SwiftPM, or Bazel are invoked.
