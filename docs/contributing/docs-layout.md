# Gimle-Palace — Docs Layout

> Extracted from former `CLAUDE.md` "Docs layout" + "Pinning" sections during
> UAA Phase H1 CLAUDE.md decompose (2026-05-17).

## Conventional locations

- `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` — design specs (Board
  output). Revisions keep the old file with a deprecation banner at
  the top; new revisions add `-rev3` suffix.
- `docs/superpowers/plans/YYYY-MM-DD-GIM-<N>-<slug>.md` — TDD
  implementation plans, one per issue. `GIM-NN` placeholder is
  swapped for the real issue number when CTO formalizes in Phase 1.1.
- `docs/postmortems/YYYY-MM-DD-<incident>.md` — one file per incident
  in the three-gate analysis format established by GIM-48.
- `docs/research/` — external library verification, competitive
  analysis, extractor inventory, etc. Treat older research docs as
  historical; verify library APIs against the installed version
  before reusing any claim.
- `docs/contributing/` — Gimle-Palace developer guide fragments
  (branch flow, docs layout, paperclip team workflow).
- `docs/runbooks/` — operator step-by-step procedures (deploys,
  rollbacks, extractor onboarding).
- `docs/palace-mcp/` — palace-mcp-specific reference (extractors,
  ADR v2, env vars, foundation substrate).
- `services/palace-mcp/README.md` — service-level deploy + mounts +
  Docker compose + environment.

## Pinning

When editing specs or plans, always reference the commit SHA or
branch state the artefact is grounded in — do not assume "current
develop" still means what it meant when a future reader lands here.
Cite a predecessor slice's merge SHA in spec headers.
