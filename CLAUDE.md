# Gimle Palace — Developer Guide

This file is a thin index. Detailed content was extracted into focused
docs during UAA Phase H1 CLAUDE.md decompose (2026-05-17).

## Contributing

- [Branch Flow](docs/contributing/branch-flow.md) — single-mainline `develop`,
  iron rules, branch protection, release-cut procedure.
- [Docs Layout](docs/contributing/docs-layout.md) — where specs / plans /
  postmortems / runbooks live + pinning rule.
- [Paperclip Team Workflow](docs/contributing/paperclip-team-workflow.md) —
  phase choreography (1.1 → 4.2), operator auto-memory.

## palace-mcp

- [palace-mcp README](services/palace-mcp/README.md) — service-level tools,
  production deploy on iMac, AGENTS.md deploy, Docker compose profiles,
  environment, mounting project repos for `palace.git.*`.
- [Extractors + Bundles + ADR reference](docs/palace-mcp/extractors.md) —
  full extractor catalog, per-extractor operator workflows, ADR v2
  contract, foundation substrate + env vars.

## Runbooks

- [UAA live deploy](docs/runbooks/uaa-live-deploy.md) — operator
  step-by-step for trading / uaudit / gimle deploys + 7-day stability
  gate + rollback.
- Other runbooks under `docs/runbooks/`.
