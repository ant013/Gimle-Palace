# SwiftPM contract

- Date: `2026-05-06`

## Command

```bash
/usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*)' /usr/bin/swift package dump-package --package-path <ABSOLUTE_PATH>
```

## Validation

Schema: `contracts/swiftpm-dump-package-v1.schema.json`

Sample: `contracts/swiftpm-dump-package-v1.sample.json`

JSON Schema validation: `PASS`

Products: `2`

Targets: `3`

## Security notes

- Used `swift package dump-package`; no build/test command was invoked.
- Command ran under sandbox network deny with a sanitized environment.
- Output is preserved as a sanitized committed sample for parser-contract review.

## API drift

Installed `swift 5.8.1` rejects `--type json`; the local equivalent command is `swift package dump-package --package-path <root>`, which still returns JSON.
Sandboxed SwiftPM introspection failed locally because `xcrun --show-sdk-platform-path` could not resolve `PlatformPath` from the Command Line Tools installation.

## Sources

- Local tool: `swift --version` and `swift package dump-package --help` on 2026-05-06
- Official docs: https://docs.swift.org/package-manager/PackageDescription/PackageDescription.html
