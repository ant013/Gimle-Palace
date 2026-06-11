## Wallet Radar Runtime Scope

This bundle inherits the shared Codex role text above. The base text was
authored for Gimle/CX; for **Wallet Radar** the substitutions below take
precedence over any conflicting reference.

- **Paperclip company/project**: Wallet Radar (`UNS`).
- **Runtime agent**: `{{agent.agent_name}}`.
- **Workspace cwd**: `{{paths.primary_repo_root}}`.
- **Source repo**: `https://github.com/horizontalsystems/wallet-radar`, mirrored
  read/write at `{{paths.primary_repo_root}}`.
- **Project domain**: wallet/blockchain source and news intelligence.
- **Mainline**: `main`. No `develop`.
- **Branch naming**: `feature/<phase-id>-<slug>` where phase IDs come from
  `ROADMAP.md` (`wr-0`, `wr-1`, ...).
- **Specs**: `docs/specs/<phase-id>-<slug>.md`.
- **Plans**: `docs/plans/<phase-id>-<slug>-plan.md`.
- **Roadmap**: `ROADMAP.md` at repo root.
- **Workflow reference**: `paperclips/projects/wallet-radar/WORKFLOW.md` in the
  Gimle-Palace Paperclip assembly repo, plus `docs/paperclip/WORKFLOW.md` in the
  Wallet Radar repo after bootstrap.
- **Primary codebase-memory project**: `{{agent.primary_codebase_memory_project}}`.
- **Required base MCP set**: `codebase-memory`, `context7`, `serena`, `github`,
  `sequential-thinking`.
- **Instruction entry file**: each Wallet Radar Codex role uses its own managed
  bundle file (`WalletRadarCEO.md`, `WalletRadarCTO.md`, etc.) because the
  default `AGENTS.md` path is shared across this all-Codex team.

### Substitution Table

| Base text reference | Wallet Radar equivalent |
|---|---|
| `develop` integration branch | `main` |
| `feature/GIM-N-<slug>` or `feature/UNS-N-<slug>` | `feature/<phase-id>-<slug>` |
| `docs/superpowers/specs` | `docs/specs` |
| `docs/superpowers/plans` | `docs/plans` |
| `/Users/Shared/Ios/Gimle-Palace` production checkout | `{{paths.primary_repo_root}}` |
| Gimle/CX or Trading agent names | Wallet Radar roster below only |
| `palace.*`, `trading.*`, project MCP namespace | Not available in Wallet Radar V1; use base MCPs only |

### V1 Scope Boundary

Wallet Radar V1 covers source/news intelligence for wallet apps, blockchain
clients, protocol docs, official news, forums, release feeds, health/digest,
replay, deterministic analysis, and Paperclip dry-run.

Do not expand V1 into on-chain monitoring, app stores, social production feeds,
LLM analysis, MCP server, Neo4j projection, Postgres, or live Telegram delivery
unless the active child issue explicitly approves that work.

### Agent Roster

Use these formal mentions in handoffs. Do not copy UUIDs from other Paperclip
companies.

| Role | Formal mention |
|---|---|
| CEO | `[@WalletRadarCEO](agent://{{bindings.agents.WalletRadarCEO}}?i=crown)` |
| CTO | `[@WalletRadarCTO](agent://{{bindings.agents.WalletRadarCTO}}?i=shield)` |
| CodeReviewer | `[@WalletRadarCodeReviewer](agent://{{bindings.agents.WalletRadarCodeReviewer}}?i=eye)` |
| PythonEngineer | `[@WalletRadarPythonEngineer](agent://{{bindings.agents.WalletRadarPythonEngineer}}?i=code)` |
| QAEngineer | `[@WalletRadarQAEngineer](agent://{{bindings.agents.WalletRadarQAEngineer}}?i=bug)` |

### Workflow Chain

Wallet Radar runs two loops:

- **Outer loop**: one parent walker issue assigned to WalletRadarCTO. CTO scans
  `ROADMAP.md`, picks the first `### WR.N <Name>` heading without `**Status:** ✅`
  in the next 3 lines, spawns one child, then waits for that child to close.
- **Inner loop**: CTO spec → CodeReviewer spec review → CTO plan →
  PythonEngineer implementation → CodeReviewer code review → QAEngineer smoke →
  CTO roadmap status line + squash merge + child close + parent advance.

Hard rules:

- one child at a time;
- no direct push to `main`;
- `ROADMAP.md` status line lands through the implementation PR;
- child is not closed until the PR is squash-merged and `main` contains the
  matching `**Status:** ✅ Implemented - PR #N (...)` line.
