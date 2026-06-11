# Wallet Radar workflow

Authoritative project workflow for Wallet Radar Paperclip agents. Shared role
fragments remain authoritative for general agent discipline; this file defines
only Wallet Radar project behavior.

---

## Repo conventions

- **Repository**: `https://github.com/horizontalsystems/wallet-radar`
- **iMac checkout**: `/Users/Shared/WalletRadar`
- **Mainline**: `main`; no `develop`
- **Branch naming**: `feature/<phase-id>-<slug>`
- **Specs**: `docs/specs/<phase-id>-<slug>.md`
- **Plans**: `docs/plans/<phase-id>-<slug>-plan.md`
- **Roadmap**: `ROADMAP.md` at repo root

Wallet Radar V1 is source/news intelligence. Do not add on-chain monitoring,
app stores, social production feeds, LLM analysis, MCP server, Neo4j, Postgres,
or live Telegram delivery unless the active child issue explicitly says so.

---

## Agent instruction deployment

Wallet Radar uses Codex for all five roles. In the current Paperclip managed
bundle implementation, the default `AGENTS.md` bundle path is shared across the
Codex target. Therefore each Wallet Radar agent uses a project-specific entry
file declared in `paperclip-agent-assembly.yaml`:

| Agent | Entry file |
|---|---|
| WalletRadarCEO | `WalletRadarCEO.md` |
| WalletRadarCTO | `WalletRadarCTO.md` |
| WalletRadarCodeReviewer | `WalletRadarCodeReviewer.md` |
| WalletRadarPythonEngineer | `WalletRadarPythonEngineer.md` |
| WalletRadarQAEngineer | `WalletRadarQAEngineer.md` |

Deployers must upload the generated bundle to that entry file and then PATCH
`/api/agents/:agentId/instructions-path` with the same path. Do not deploy all
Wallet Radar Codex agents to the default `AGENTS.md` path; the last upload will
overwrite the active prompt for the others.

---

## Topology

### Outer loop: roadmap walker parent

- One long-lived parent issue.
- Assignee: WalletRadarCTO.
- CTO scans `ROADMAP.md` top-to-bottom.
- For each `### WR.N <Name>` heading, inspect the next 3 lines.
- If `**Status:** ✅` is present, skip it.
- First heading without that marker is the next child.
- Spawn exactly one child issue with `parentId` set to the walker issue UUID.
- Wait for the child to close before creating another child.

If all `### WR.N` headings are marked done, CTO posts a summary comment on the
parent and stops. If the order is ambiguous, CTO posts the ambiguity on the
parent and waits for the operator.

### Inner loop: child issue

| # | Phase | Owner | Exit |
|---|---|---|---|
| 1 | Spec | WalletRadarCTO | Spec file committed/pushed, hand off to CodeReviewer |
| 2 | Spec review | WalletRadarCodeReviewer | Findings posted, hand off to CTO |
| 3 | Plan | WalletRadarCTO | Plan file committed/pushed, hand off to PythonEngineer |
| 4 | Implement | WalletRadarPythonEngineer | Implementation PR opened, hand off to CodeReviewer |
| 5 | Code review | WalletRadarCodeReviewer | Review and command evidence posted, hand off to QAEngineer |
| 6 | Smoke | WalletRadarQAEngineer | Acceptance evidence posted, hand off to CTO or back to PE/CTO |
| 7 | Merge | WalletRadarCTO | Roadmap status line committed, PR squash-merged, child closed |

---

## Roadmap status line

At Phase 7, CTO adds this line directly under the implemented heading:

```markdown
### WR.N Name
**Status:** ✅ Implemented - PR #<N> (<YYYY-MM-DD>, commit `<SHA>`)
```

The status line must land on `main` via the same implementation PR. Do not
create a separate roadmap-only PR and do not push directly to `main`.

---

## Merge gate

Before closing a child, WalletRadarCTO verifies:

- PR exists from the child feature branch to `main`;
- PR includes the matching `ROADMAP.md` status line;
- CodeReviewer approval or explicit non-code review evidence exists;
- QA PASS or approved documentation-only QA evidence exists;
- `gh pr checks <PR>` exits 0, or CTO records that no required checks exist;
- PR head SHA is captured.

Merge command:

```bash
gh pr merge <PR> --squash --match-head-commit=<HEAD_SHA> --delete-branch
```

After merge, CTO pulls `main`, verifies the roadmap status line is present, then
sets the child `status=done` and wakes the parent walker.

---

## Atomic handoff

Every phase transition uses one Paperclip PATCH:

```json
{
  "status": "in_progress",
  "assigneeAgentId": "<next-agent-uuid>",
  "comment": "<exit evidence + next phase instruction>"
}
```

`@mention` text is decorative; `assigneeAgentId` is the wake mechanism.
