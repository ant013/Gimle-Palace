---
description: Assemble role-scoped context snapshot for current slice
argument-hint: <role> [<slice-id>]
---

Call palace.memory.prime MCP tool with the following parsed arguments:

- role = first word of $ARGUMENTS (validate against: operator, cto, codereviewer, pythonengineer, opusarchitectreviewer, qaengineer)
- slice_id = optional second word of $ARGUMENTS; if absent, omit the arg (tool will auto-detect from current git branch)

Then display the returned `content` field verbatim to the user.

If $ARGUMENTS is empty, prompt the user: Usage: /prime <role> [<slice-id>]. Example: /prime pythonengineer or /prime cto GIM-95a.
