# Role Audit — 2026-05-05

Read-only audit data for `core/fix-agent-infra-slim` plan
(`docs/superpowers/plans/2026-05-05-agent-infra-slim.md`).

## Files

| File | Purpose |
|---|---|
| `role-deep-audit.py` | Per-role inline-duplicate + dead-subagent-ref detector. Reads all 20 role files, cross-references against shared fragments + invocation data. |
| `role-deep-audit.json` | Output of above — full per-role analysis. |
| `bundle-audit.json` | Per-role expected-vs-actual fragment inclusion (from `instruction-coverage.matrix.yaml`). |
| `agent-tool-audit.py` | iMac session jsonl parser — counts subagent + skill invocations per role across 464 paperclip sessions (last ~30 days). |
| `paperclip-agent-activity.py` | Paperclip API issue-counter — issues per agent (claude + codex) sampled from /api/companies/.../issues. |

## Reproducing

### Per-role inline + dead-ref audit (operator Mac)

```bash
python3 docs/research/2026-05-05-role-audit/role-deep-audit.py
```

### iMac runtime tool-call audit (run on iMac)

```bash
ssh imac-ssh.ant013.work
scp docs/research/2026-05-05-role-audit/agent-tool-audit.py imac:/tmp/
ssh imac-ssh.ant013.work 'python3 /tmp/agent-tool-audit.py'
```

### Paperclip API issue audit

```bash
TOKEN=$(cat ~/.paperclip-token)
curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://paperclip.ant013.work/api/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/issues?limit=500" \
  | python3 docs/research/2026-05-05-role-audit/paperclip-agent-activity.py
```

## Key findings (2026-05-05)

### Tool invocations across 464 sessions (~30 days)

- **40 subagent calls** total. 60% Explore (built-in). voltagent: 5 calls (4× qa-sec:code-reviewer + 1× research:search-specialist). pr-review-toolkit: 1 call.
- **464 skill calls**. 97% paperclip (workflow). Remaining: superpowers (writing-plans, executing-plans, TDD, receiving-code-review).

### Dead subagent references (in role .md files but never invoked)

- ~100 dead refs across 20 roles
- Top dead: `superpowers:verification-before-completion` (10 roles), `superpowers:systematic-debugging` (9 roles), `voltagent-qa-sec:security-auditor` (7 roles, 0 calls)
- `voltagent-research:search-specialist` referenced in 8 roles but only ResearchAgent actually calls it → 7 dead refs

### Inline duplications

- ONLY claude:code-reviewer has inline-vs-fragment duplications (2 sections — Plan-first discipline + Phase 3.1 file-structure check)
- All other 19 roles have role-specific inline content (no dedup needed)

### Cross-team parity

- Only 1 anomaly: `claude:code-reviewer` (14 fragments) vs `codex:cx-code-reviewer` (6 fragments) — Δ +8 missing in codex
- 8 other paired roles have parity (Δ=0)

### iMac user-level subagents (separate from plugin)

- `~/.claude/agents/code-reviewer.md` — used 6 calls, user-level, only on iMac
- `~/.claude/agents/deep-research-agent.md` — used 3 calls, user-level, only on iMac

These survive plugin re-curation.
