# fullAudit: minimal runtime MCP readiness contract

## Decision

The operator selected the minimal viable runtime MCP contract.  fullAudit will
require only `codebase-memory` and `context7` at runtime. Serena,
`sequential-thinking`, and GitHub MCP are optional: instructions already use
the safe `rg`/ordinary Git fallback when they are absent.

## Scope

- Change the fullAudit manifest's required MCP set to the two verified runtime
  servers.
- Make smoke derive expected MCP markers from the project manifest rather than
  a global hardcoded five-server list, normalizing hyphens to the Codex runtime
  underscore namespace.
- Add focused tests for the fullAudit contract and marker normalization.
- Deploy to iMac and rerun one controlled smoke; create the roadmap issue only
  if it passes.

## Non-goals

- Do not enable sandbox bypass, add a GitHub token, or remove the global
  optional MCP configurations.
- Do not weaken audit instructions or re-audit completed BitcoinCore.

## Acceptance criteria

1. fullAudit declares only `codebase-memory` and `context7` as runtime
   required MCP servers.
2. Smoke accepts `mcp__codebase_memory` for manifest entry
   `codebase-memory` and `mcp__context7` for `context7`.
3. Other projects retain their own manifest-defined requirements.
4. Focused tests, manifest validation, CI, and one full controlled iMac smoke
   pass with only its own disposable issue cleanup.

## Verification plan

Run focused smoke/fullAudit tests, build and validate the manifest, verify CI,
then retain and inspect the iMac smoke log before creating any roadmap issue.
