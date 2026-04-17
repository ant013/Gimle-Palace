# PR Review Flow — Gimle

Describes the two-tier review process for feature PRs targeting `develop`.
Release PRs (`develop → main`) follow the existing CTO-approval rule in `CLAUDE.md`.

## Scope

This flow applies to **feature PRs targeting `develop`** that contain code or infra changes
(`src/`, `tests/`, `compose.yaml`, `paperclips/`, `Dockerfile`).

**Opt-out:** doc-only PRs (no changes outside `docs/`, `*.md`, `*.yaml` plans) may merge with
Sonnet-only review. Opus invocation is optional for doc-only PRs.

## Lifecycle

```
feature/GIM-N cut from develop
       │
       ▼
engineer commits + pushes
       │
       ▼
PR opened against develop (title: conventional commit + GIM-N reference)
       │
       ▼
Sonnet CodeReviewer — mechanical compliance pass
  (compliance checklist, CI checks, plan-first discipline)
       │
       ├─ REQUEST CHANGES → engineer fixes → re-review loop
       │
       ▼
Sonnet APPROVE + handoff comment on Paperclip issue:
  @OpusArchitectReviewer architectural pass on PR #N please. Context: <scope>.
       │
       ▼
Opus OpusArchitectReviewer — architectural pass
  (docs-first via context7, SDK conformance, subtle-pattern detection)
       │
       ├─ REQUEST CHANGES (CRITICAL) → block + fix PR loop
       │
       ▼
merge-gate evaluation (table below)
       │
       ▼
merge to develop
```

## Handoff comment template (copy-pasteable)

CodeReviewer's last comment on APPROVE MUST end with:

```
## CodeReviewer verdict: APPROVE
[one-line summary]

Full checklist: [link to compliance checklist comment]

@OpusArchitectReviewer architectural pass on PR #<N> please. Context: <one-line scope>.
```

Opus wakes automatically via the Paperclip @-mention — no routine or webhook needed.

## Opus output expectation

- Docs-first analysis (context7 lookups listed)
- Structured findings: CRITICAL / WARNING / NOTE, each with `file:line` + official doc URL citation
- Cross-check section: what CodeReviewer caught vs unique Opus findings
- Final verdict: `APPROVE | REQUEST CHANGES | REJECT`
- Cross-post: Opus posts summary comment on GitHub PR thread

## Merge-gate table

| Sonnet verdict | Opus verdict | Action |
|---|---|---|
| APPROVE | APPROVE | Merge allowed |
| APPROVE | REQUEST CHANGES (CRITICAL) | Block until fix PR + Sonnet + Opus re-APPROVE |
| APPROVE | REQUEST CHANGES (WARNING only) | CTO files follow-up issue; merge allowed |
| APPROVE | REJECT | Escalation to Board; merge blocked |
| REQUEST CHANGES | — | Opus not yet invoked; fix Sonnet findings first |

## Conflict adjudication

Sonnet and Opus disagree on the same finding:
- **Default:** CTO adjudicates on the Paperclip issue.
- **If CTO authored the plan under review:** Board adjudicates (Opus bypasses CTO for red-team independence).

## Retroactive reviews

CTO may `@OpusArchitectReviewer` on any merged PR's Paperclip issue for a post-hoc architectural
review. Findings feed backlog issues (never retroactively block already-merged code).

## Release flow

`develop → main` release PRs follow the existing CTO-approval rule defined in `CLAUDE.md §Branch Flow`.
Opus is not invoked on release PRs by default (release = already-reviewed code bundled).
