# ThorChainKit Roadmap Walker

This is the authoritative ownership and transition contract for the five-agent
ThorChainKit team. It is dormant after bootstrap: bootstrap creates no roadmap issue
and no product child issue. Activation requires a later explicit operator instruction.

## Outer loop: ThorChainCEO only

1. Read the live parent issue and stop on a closed, foreign, or stale wake.
2. If one active child exists, verify the parent is blocked by exactly that
   child and stop.
3. Fetch and fast-forward `origin/main`, then scan `ROADMAP.md` top-to-bottom.
4. A slice is complete only when a valid `**Status:** ✅` line occurs within the
   next three lines on `origin/main`.
5. Create exactly one child assigned to `ThorChainCTO`.
6. POST selection evidence, PATCH the parent to `blocked` with that one child,
   perform one read-only verification, and STOP.
7. Never write a spec, plan, code, or merge from the parent run.

## Inner loop: ThorChainCTO owns one child

1. CTO creates a fresh feature branch from `main`, writes the slice spec, and
   pushes the spec-only commit.
2. CodeReviewer performs adversarial spec review and, when required, runs the
   three bounded read-only Codex review lanes.
3. CTO resolves findings and writes the concrete implementation plan.
4. The issue becomes blocked until explicit user approval of the delivered
   analog-driven-change design. Internal agent approval is insufficient.
5. SwiftEngineer implements test-first and opens a PR to `main`.
6. CodeReviewer reviews the exact PR head and records commands and results.
7. QA independently verifies the same head. Kit UI acceptance and Maestro run
   only in the ThorChainKit `iOS Example` when the slice requires them.
8. CTO verifies review and QA evidence, adds the roadmap marker in the same PR,
   squash-merges without co-author trailers, verifies `origin/main`, and closes
   the child.

Only one child may be active. CEO never substitutes for CTO, and CTO never
substitutes for reviewer, implementer, or QA.

## Atomic handoff

Every transition uses this exact order:

1. Push the phase artifact or commit.
2. `POST /api/issues/{id}/comments` with evidence ending in the formal next-owner
   mention; a non-2xx response blocks the handoff.
3. `PATCH /api/issues/{id}` with the next assignee and status.
4. Perform one read-only verification of assignee and status.
5. `STOP` the current run.

A mention is not ownership transfer. HTTP 409 is an execution-lock conflict and
must not be bypassed with database writes.

## Role boundaries

- CEO: outer roadmap selection, parent blocker, stop/resume, status only.
- CTO: slice architecture, post-review plan, merge gate only.
- CodeReviewer: spec/code review; no implementation and no merge.
- SwiftEngineer: tests, implementation, PR; no approval and no merge.
- QAEngineer: independent acceptance; no implementation fixes and no merge.

The autonomous walker remains off until explicitly activated after live team
acceptance.
