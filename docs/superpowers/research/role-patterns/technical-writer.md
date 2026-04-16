# Technical Writer — Research Notes

**Research date:** 2026-04-16
**Purpose:** inform `paperclips/roles/technical-writer.md` for Gimle-Palace (Slice #8)
**Target deployment:** Gimle TechnicalWriter — operational docs (install guides per profile, runbooks, MCP docs, demo scripts) for Docker Compose + Neo4j + MCP stack

## 1. Sources reviewed

| Source | Stars | Length | Signal |
|---|---|---|---|
| VoltAgent `documentation-engineer` | ~17k | ~80 lines | Diataxis framework, docs-as-code, runnable examples, ADR format |
| VoltAgent `technical-writer` | ~17k | ~70 lines | Audience analysis, web-doc oriented (weak for runbooks) |
| wshobson `tutorial-engineer` | ~33k | ~90 lines | **Verification checkpoints**, progressive disclosure |
| wshobson `docs-architect` | ~33k | ~80 lines | Long-form system docs, "why behind decisions" |
| wshobson `reference-builder` | ~33k | ~70 lines | API reference specialization (not relevant) |
| garrytan `/document-release` skill | ~73k | ~50 lines | Release-pipeline integration, diff-driven updates |
| alirezarezvani `/runbook-generator` | — | ~40 lines | **Runbook skeleton, copy-pasteable commands** |
| SkeltonThatcher run-book-template | — | ~200 lines | **Most complete operational coverage** (SLA, backup, failover, DST) — structural reference |
| VoltAgent `readme-generator` | ~17k | ~60 lines | **Zero-hallucination protocol** (manifest scan, verified commands) |
| rohitg00 `/onboard` | ~1.3k | ~50 lines | docker-compose scan, exact commands not placeholders |
| addyosmani `documentation-and-adrs` | ~16k | ~60 lines | ADR structure |
| dandye/ai-runbooks | — | ~80 lines | Role-based activation, atomic/meta-skills |

12 sources, 2 lagers identified.

## 2. Community gap

Никто не покрывает Gimle-точный кейс: **operational docs для compose stack с verify loop "install → curl /health"**. Существующие — два лагеря:
- **Web/API docs** (documentation-engineer, technical-writer, reference-builder) — отлично для refs, плохо для ops
- **Tutorial/onboarding** (tutorial-engineer, /onboard, readme-generator) — близко к install guides, но без verification loop

Runbook-prompts (SkeltonThatcher, runbook-generator, ai-runbooks) — structural references, не Claude prompts.

## 3. 3 main принципа из community → Gimle template

### 3.1 Zero-hallucination (readme-generator + /onboard)

Команды извлекаются из **существующих файлов** (compose, .env.example, Justfile), не выдумываются. Никаких "обычно порт 8080" — всегда `grep -n 8080 docker-compose.yml`. Каждый flag verified.

### 3.2 Time-to-first-success + verification checkpoints (tutorial-engineer + runbook-generator)

Каждый guide = measurable cycle: prerequisites → step → expected output → step → expected output → success metric. **Time-to-first-success ≤10 min** для install guide, иначе guide сломан.

### 3.3 Docs-as-code matrix (documentation-engineer + SkeltonThatcher)

Документация — **матрица** rows × cols (doc-type × profile). НЕ один guide "для всех" — это hallucination генератор. Каждая ячейка — отдельный verified scenario.

## 4. Gimle-specific (нет в community)

- **Profile-aware install guides** — review / analyze / full / with-paperclip / client. Разные команды.
- **MCP protocol docs** для palace-mcp — community не покрывает MCP spec
- **Neo4j backup/restore runbook** — generic templates есть, Neo4j-specific нет
- **First-run demo script** — install → populate sample data → first MCP query → verify

Все 4 — primary scope для Gimle TechnicalWriter slice #8.

## 5. Final template structure (90 lines)

1. Role + scope (1-line)
2. 4 principles (zero-hallucination, time-to-first-success, copy-paste-safety, verification-after-each-step)
3. Output catalogue (6 doc types × paths)
4. Profile/topology matrix concept
5. Verification protocol (5 steps, fresh-checkout test обязателен)
6. Compliance checklist (8 items)
7. MCP/Subagents/Skills mapping
8. Fragment includes (karpathy + escalation + pre-work + heartbeat + git + worktree + language)

## 6. Decision rationale

- Не копируем VoltAgent technical-writer — он web-doc oriented, не подходит
- Не копируем reference-builder — это API ref generator, у нас MCP не REST
- Не копируем docs-architect — это long-form, нам нужны короткие actionable guides
- **Composite:** zero-hallucination (readme-generator) + verification (tutorial-engineer) + matrix (documentation-engineer + SkeltonThatcher) + Gimle-specific scope (4 уникальных)
