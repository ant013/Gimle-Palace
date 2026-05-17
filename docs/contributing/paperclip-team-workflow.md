# Gimle-Palace — Paperclip Team Workflow

> Extracted from former `CLAUDE.md` "Paperclip team workflow" + "Operator
> auto-memory" sections during UAA Phase H1 CLAUDE.md decompose
> (2026-05-17).

## Phase choreography

Product slices of meaningful size (>200 LOC or cross-cutting) go
through the paperclip agent team rather than being implemented
inline. Canonical phase sequence:

- **1.1 Formalize** (CTO) — verify Board's spec+plan paths, swap the
  `GIM-NN` placeholder, reassign to CodeReviewer.
- **1.2 Plan-first review** (CodeReviewer) — validate every task has
  concrete test+impl+commit; flag gaps; APPROVE → reassign to
  implementer.
- **2 Implement** (MCPEngineer / PythonEngineer / …) — TDD through
  plan tasks on `feature/GIM-<N>-<slug>`; push frequently.
- **3.1 Mechanical review** (CodeReviewer) — paste
  `uv run ruff check && uv run mypy src/ && uv run pytest` output in
  APPROVE; no "LGTM" rubber-stamps.
- **3.2 Adversarial review** (OpusArchitectReviewer) — poke holes;
  findings addressed before Phase 4.
- **4.1 Live smoke** (QAEngineer) — on iMac; real MCP tool call + CLI
  + direct Cypher invariant. Evidence comment authored by
  QAEngineer.
- **4.2 Merge** — squash-merge to develop after CI green. No admin
  override.

Phase-handoff discipline is encoded in the shared-fragments
`handoff/basics.md` + `handoff/phase-orchestration.md` (submodule
`paperclip-shared-fragments`, composed into every role's `AGENTS.md`
via the Phase B profile builder). Reassign explicitly between phases —
`status=todo` between phases is forbidden.

## Operator auto-memory

The operator's Claude Code session maintains an auto-memory store
alongside this repo. A fresh session should look there for current
slice status, paperclip API tokens, known library pitfalls, incident
lessons, and deploy notes. The repo itself assumes operator memory
exists but does not reference any single memory file by path.
