# Gradle contract

- Date: `2026-05-06`

## Command

```text
No project-level Gradle command executed in this spike revision.
```

## Validation

Schema: `contracts/gradle-tooling-v1.schema.json`

Sample: `contracts/gradle-tooling-v1.sample.json`

JSON Schema validation: `PASS`

Projects: `3`

Tasks: `3`

## Security notes

- Project-level Gradle interrogation is intentionally unresolved in this spike revision.
- The previous trusted-helper-task approach was removed because it still executed a task action and did not satisfy the Step 2 `no build task/action execution` rule.
- The committed contract sample remains reviewable, but Step 3 stays blocked until a configuration-only or Tooling-API-based capture is proven.

## Sources

- Local tool: `gradle --version` on 2026-05-06
- Official docs: https://docs.gradle.org/current/userguide/command_line_interface_basics.html
- Official dry-run docs: https://docs.gradle.org/current/userguide/command_line_interface.html#sec:command_line_execution_options

## Observed output

```text
Gradle contract sample retained; live project capture intentionally not executed.
```
