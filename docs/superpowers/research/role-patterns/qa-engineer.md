# QA Engineer — Research Notes

**Research date:** 2026-04-16
**Purpose:** inform `paperclips/roles/qa-engineer.md` for Gimle-Palace (Slice #7)
**Target deployment:** Gimle QAEngineer (Python/FastAPI + Docker Compose + Neo4j/testcontainers; gate between merge and prod)

## 1. Sources reviewed

| Source | Stars | Size | Signal |
|---|---|---|---|
| **Medic `paperclips/roles/qa-engineer.md`** | author's own (field-tested) | 62 lines | **primary field model** — adversarial skeptic + edge cases matrix + compliance checklist |
| wshobson/agents | ~33k | 80-100 lines | progressive disclosure skills; `unit-testing` plugin + `python-testing-patterns` |
| addyosmani/agent-skills (TDD) | ~16k | ~60 lines | **"Real > Fakes > Stubs > Mocks" hierarchy** + Test State Not Interactions |
| VoltAgent qa-expert | ~17k | ~80 lines | 8 QA domains; explicit coverage/automation KPI targets |
| VoltAgent test-automator | ~17k | ~80 lines | `<1% flaky` SLA; self-healing tests; framework design |
| rohitg00 qa-automation | ~1.3k | ~71 lines | **Docker Compose CI pattern**; testing pyramid 70/20/10; transaction rollback isolation |
| fugazi/test-automation | ~97 | 11 агентов | Flaky Test Hunter — dedicated specialist |
| garrytan/gstack | ~72k | 10 lines | `/qa` browser-first loop (Playwright-style, not applicable for MCP/backend) |
| LambdaTest/agent-skills | — | 46 skills | pytest as 1 of 15 unit-testing framework skills |

## 2. Gimle-specific gaps vs Medic baseline

Medic's QA template was built for KMP (Kotlin) + Supabase (pgTAP) + Android/iOS mobile. Gimle stack is different:

| Medic pattern | Gimle equivalent / gap |
|---|---|
| `kotlin.test + Turbine` | `pytest + pytest-asyncio` |
| `pgTAP` for DB | **GAP** — no DB-layer test framework; use testcontainers for Neo4j integration |
| `./gradlew :shared:allTests` | `uv run pytest` |
| Cross-platform parity (Android+iOS) | **N/A** — Gimle is single-deploy, no mobile |
| Offline edge cases | **N/A** — server-side, always online |
| PillBox/Kit parity verification | **N/A** |
| — | **NEW: Docker Compose smoke gate** (critical — GIM-10 incident) |
| — | **NEW: testcontainers lifecycle** (Neo4j stateful, no rollback) |
| — | **NEW: Test doubles hierarchy** (Python makes over-mocking trivial) |

## 3. Top-3 additions (from community research)

### 3.1 Docker Compose smoke gate (rohitg00 + CI patterns)

**Evidence from GIM-10:** CodeReviewer APPROVE'd PR #2 on static review + unit tests. InfraEngineer merged without live smoke. Only Board bonus-run caught real state (all 3 profiles green). **Next time could ship broken.**

Pattern: `docker compose up -d --wait` (Compose V2+ healthchecks) + curl /health + /healthz + down. Evidence in PR comment.

### 3.2 Testcontainers lifecycle (VoltAgent test-automator adapted to Neo4j)

Neo4j doesn't support TRUNCATE or transaction rollback like Postgres. State resets via `MATCH (n) DETACH DELETE n` in autouse fixture. Container scope = session (startup cost ~30s).

### 3.3 "Real > Fakes > Stubs > Mocks" (addyosmani TDD)

Python's `unittest.mock` makes over-mocking trivial. Test passes while integration is broken (e.g., mock `neo4j.Driver` — test never touches real driver — neo4j auth bug undetected).

Explicit hierarchy in role prompt prevents this — use real dependency via testcontainers, fall back to mocks only when real is impossible.

## 4. Retained from Medic

- Adversarial skeptic principle ("не доверяй — проверяй")
- Regression-first (failing test → fix)
- Compliance checklist (mechanical, no rubber-stamp)
- Silent-failure zero-tolerance
- MCP wiring pattern (serena, github, context7)
- Subagent catalog (qa-expert, test-automator, debugger, error-detective)
- Skills: TDD, systematic-debugging, verification-before-completion

## 5. Dropped from Medic (not applicable to Gimle)

- Android/iOS cross-platform parity
- SQLDelight migration testing
- Turbine (Kotlin Flow testing)
- pgTAP (Postgres)
- Offline mode edge cases
- Kit/PillBox parity check

## 6. Final template structure (80 lines)

~20 lines more than Medic — justified by 3 gaps. Sections:

1. Role statement (1-line)
2. Principles (5 bullets, including Real > Fakes hierarchy)
3. Test infrastructure table (5 rows Gimle stack)
4. **Compose smoke gate (NEW)** — procedure + evidence requirement
5. **Testcontainers lifecycle (NEW)** — fixture scope + state reset
6. Edge cases matrix (8 categories adapted for Gimle: no offline, no cross-platform, add Docker/Secrets)
7. Compliance checklist (10 items, includes `asyncio_mode=auto` check)
8. MCP / Subagents / Skills (mirrors Medic pattern, Python-adapted)
9. Fragment includes (karpathy, escalation-blocked, pre-work, git, worktree, heartbeat, language)

## 7. Sources

See Section 1 table. 9 prompts reviewed + targeted web searches for pytest-asyncio/httpx.ASGITransport/testcontainers Neo4j patterns (docs, not agent prompts — stack-specific tooling).
