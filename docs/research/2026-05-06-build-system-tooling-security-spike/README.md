# Build system tooling + security spike (2026-05-06)

## Summary

- Recommendation: `NO-GO`
- Date: `2026-05-06`
- Scope: Step 2 only, no production extractor code

## Tool versions

- `python3`: Python 3.9.6
- `gradle`: ------------------------------------------------------------
Gradle 9.3.1
------------------------------------------------------------

Build time:    2026-01-29 14:15:01 UTC
Revision:      44f4e8d3122ee6e7cbf5a248d7e20b4ca666bda3
- `swift`: Apple Swift version 5.8.1 (swiftlang-5.8.0.124.5 clang-1403.0.22.11.100)
Target: x86_64-apple-darwin22.6.0
- `bazel`: not installed
- `sandbox-exec`: /usr/bin/sandbox-exec

## Commands

```bash
./run-spike.sh sandbox-preflight --require-sandbox --write evidence/sandbox-preflight.md
./run-spike.sh sandbox-preflight --force-unsandboxed --expect-skip build_system_unsandboxed --write evidence/skip-if-unsandboxed.md
./run-spike.sh gradle-contract --fixture throwaway-gradle --no-host-gradlew --no-wrapper-download --no-build-tasks --schema contracts/gradle-tooling-v1.schema.json --write evidence/gradle-contract.md
./run-spike.sh swiftpm-contract --fixture throwaway-swiftpm --command "swift package dump-package --type json --package-path <root>" --schema contracts/swiftpm-dump-package-v1.schema.json --write evidence/swiftpm-contract.md
./run-spike.sh bazel-contract --fixture committed-sample --commands "bazel query" "bazel aquery --output=jsonproto" --schema contracts/bazel-query-aquery-v1.schema.json --write evidence/bazel-contract.md
./run-hostile-fixtures.sh --cases env-leak,hanging-config,wrapper-download,absolute-path,bazel-cmdline-leak,timeout,unbounded-output,cancellation-cleanup --write evidence/hostile-fixtures.md
```

## Contracts

- [contracts/gradle-tooling-v1.schema.json](contracts/gradle-tooling-v1.schema.json)
- [contracts/gradle-tooling-v1.sample.json](contracts/gradle-tooling-v1.sample.json)
- [contracts/swiftpm-dump-package-v1.schema.json](contracts/swiftpm-dump-package-v1.schema.json)
- [contracts/swiftpm-dump-package-v1.sample.json](contracts/swiftpm-dump-package-v1.sample.json)
- [contracts/bazel-query-aquery-v1.schema.json](contracts/bazel-query-aquery-v1.schema.json)
- [contracts/bazel-query-aquery-v1.sample.json](contracts/bazel-query-aquery-v1.sample.json)

## Evidence

- [evidence/sandbox-preflight.md](evidence/sandbox-preflight.md)
- [evidence/skip-if-unsandboxed.md](evidence/skip-if-unsandboxed.md)
- [evidence/gradle-contract.md](evidence/gradle-contract.md)
- [evidence/swiftpm-contract.md](evidence/swiftpm-contract.md)
- [evidence/bazel-contract.md](evidence/bazel-contract.md)
- [evidence/hostile-fixtures.md](evidence/hostile-fixtures.md)

## Recommendation

The spike now proves sandbox preflight, structured unsandboxed skips, bounded hostile-output handling, schema-bounded contract samples, and wrapper/env/path redaction controls, but it still does not prove a complete sandboxed runtime path for all three ecosystems on this machine: Gradle remains intentionally unresolved until a configuration-only or Tooling-API-based capture is proven without task-action execution, SwiftPM still fails in sandbox via `xcrun`/`PlatformPath`, and Bazel is not installed locally. Production implementation across all three ecosystems should stay blocked until all three live paths are proven.

## Notes

- Gradle docs: https://docs.gradle.org/current/userguide/command_line_interface_basics.html
- SwiftPM docs: https://docs.swift.org/package-manager/PackageDescription/PackageDescription.html
- Bazel query docs: https://bazel.build/docs/query-how-to
- Bazel aquery docs: https://bazel.build/versions/7.3.0/query/aquery
