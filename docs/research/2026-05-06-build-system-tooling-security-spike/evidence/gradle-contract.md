# Gradle contract

- Date: `2026-05-06`

## Command

```bash
/usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*)' /Users/anton/.local/bin/gradle --project-dir /var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/gim215-gradle-2x5xpig6/gradle-multi-project --no-daemon --offline --console=plain -q -I /var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/gim215-gradle-2x5xpig6/gradle-probe.init.gradle buildSystemProbe -DbuildSystemProbeOutput=/var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/gim215-gradle-2x5xpig6/gradle-tooling.json
```

## Validation

Schema: `contracts/gradle-tooling-v1.schema.json`

Sample: `contracts/gradle-tooling-v1.sample.json`

Projects: `3`

Tasks: `3`

## Security notes

- Local sandbox preflight exists, but the sandboxed Gradle launcher could not resolve a Java runtime on this machine.
- Contract shape is still captured as a committed reviewer sample, but the local Gradle runtime path remains unproven.
- This is a release blocker for production Step 3 on this machine.

## Sources

- Local tool: `gradle --version` on 2026-05-06
- Official docs: https://docs.gradle.org/current/userguide/command_line_interface_basics.html

## Observed output

```text
The operation couldn’t be completed. Unable to locate a Java Runtime.
Please visit http://www.java.com for information on installing Java.
```
