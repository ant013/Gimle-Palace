# Research Agent — Research Notes

**Research date:** 2026-04-16
**Purpose:** inform `paperclips/roles/research-agent.md` for Gimle-Palace (Slice #10 — final core-team slice)
**Target:** synthesis layer для technology landscape research (Graphiti / MCP spec / Neo4j / memory frameworks / code analysis tools)

## 1. Sources reviewed

| Source | Stars | Length | Source ranking | Citations | Gap detection | Recency |
|---|---|---|---|---|---|---|
| **rohitg00 `research-analyst`** | ~12k | 72 lines | Implicit pyramid, consensus wins | **Every claim → cite** | H/M/L/SPECULATIVE per finding + follow-ups by decision impact | Obsolescence flag, time-sensitivity |
| **VoltAgent `research-analyst`** | 17.4k | 287 lines | 8 evaluation criteria, no explicit pyramid | Mentioned, no format | "Identify research gaps" | "Currency checking", no thresholds |
| **Imbad0202 `Deep Research SKILL`** | 2.9k | ~1050 lines | **7-tier formal hierarchy** (meta-analyses → expert) | **Iron Rule + verification** | 3 mechanisms (synthesis, contradictions, gaps) | No explicit cutoff, currency agent |
| wshobson `search-specialist` | 33.7k | ~280 lines | None | Source DB tracking | Failure-after-3-attempts | Update monitoring |
| ARIS `Auto-claude-code-research-in-sleep` | 6.8k | 62 skills | Cross-model adversarial | BibTeX from DBLP/CrossRef | Research Wiki w/ relations | N/A (ML papers focused) |
| AI-Research-SKILLs | 6.9k | 87 skills | Official > GitHub > prod code | Code examples | Quality over quantity | v1.4.0 march 2026 |
| XInTheDark Deep Research gist | — | ~200 lines | Primary > secondary | Numbered APA + /sources | Contradiction → investigate | Date ranges |
| VoltAgent `scientific-literature-researcher` | 17.4k | ~200 lines | Statistical power | Structured + confidence | Contradiction flagging | Recency filter |

8 sources, 3 directly applicable (rohitg00, Imbad0202, VoltAgent research-analyst).

## 2. Key insights

### 2.1 Tech-research is different from academic-research
Most prompts (Imbad0202, scientific-literature, ARIS) focus on academic literature with formal citation hierarchies. Tech research has different source dynamics: **GitHub releases > maintainer blog > community blog > HN/Reddit**. Academic pyramid не применим — нет journals для library version compatibility.

### 2.2 rohitg00 is the closest fit (72 lines, dense)
- **10-step methodology** with explicit decision context on Step 1
- **Confidence scale per finding** (H/M/L/SPECULATIVE) — not per-report
- **Follow-up questions ranked by decision impact** — exact match for Gimle pattern "research X before deciding Y"
- Compact (72 lines) — leaves room для Gimle-specific blocks

### 2.3 Imbad0202's [MATERIAL GAP] anti-hallucination protocol
- Iron Rule #1: every claim = citation
- `[MATERIAL GAP]` flag instead of filling from parametric memory
- For tech landscape (versions, recent releases) — critical anti-hallucination guard
- Adapt as `[VERSION GAP]` for Gimle (когда web search не подтвердил конкретную версию)

### 2.4 No community prompt has consumer-aware output routing
Все prompts выводят generic structured report. Gimle pattern требует другой report shape для CTO (architectural decisions) vs MCPEngineer (protocol picks) vs PythonEngineer (library choices). **Это уникальный для Gimle паттерн** — добавлено явно в template.

## 3. Top-3 community recommendations

1. **Base:** rohitg00 research-analyst (decision-context + per-finding confidence + impact-ranked follow-ups)
2. **Add anti-leakage:** Imbad0202 [MATERIAL GAP] pattern → adapt as [VERSION GAP] / [MATERIAL GAP] / [CONTRADICTION] taxonomy
3. **Search-specialist as sub-tool:** ResearchAgent оркестрирует voltagent search-specialist для retrieval, синтезирует поверх

## 4. 4 Gimle-specific blocks (not in any community prompt)

### 4.1 Tech-source tier (vs academic pyramid)
Official docs + GitHub releases > library source code > maintainer blog > community blog > HN/Reddit discussion. Consensus сильнее изолированного claim.

### 4.2 Version-pinned claims
Every library claim carries explicit version (`Graphiti 0.3.x`, `MCP spec 2024-11-05`). Version drifts → claim expires.

### 4.3 Consumer-aware output (4 audiences)
Report shape depends on consumer role:
- CTO → tradeoff matrix + decision impact follow-ups
- MCPEngineer → spec compliance + migration cost
- PythonEngineer → dependency / async / typing / maintenance
- InfraEngineer → deployment / resource / ops maturity

### 4.4 Trigger discipline
ResearchAgent не self-initiates. Triggers: CTO request / engineer ask / periodic spec evolution per CTO. Без триггера — idle.

## 5. Final template structure (~95 lines role)

1. Role + scope (5 specialization domains, NOT general)
2. Trigger discipline (3 valid triggers, no self-init)
3. 5 principles (citation, source tier, version pinning, confidence scale, recency)
4. Consumer-aware output table (4 consumers × accept criteria)
5. Gap escalation taxonomy ([VERSION GAP] / [MATERIAL GAP] / [CONTRADICTION])
6. Compliance checklist (8 items)
7. MCP/Subagents/Skills
8. Fragment includes (karpathy + escalation + heartbeat + git + worktree + language + pre-work)
