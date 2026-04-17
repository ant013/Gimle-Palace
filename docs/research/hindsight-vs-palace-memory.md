# Hindsight vs palace-memory — quick comparison (2026-04-17)

Quick find during GIM-39 gap closure. Not a full research issue — just enough to trigger decision.

## Hindsight

- **Repo:** `vectorize-io/hindsight`, MIT, by Vectorize.io (vector DB company).
- **Paper:** arxiv 2512.12818. SOTA on LongMemEval benchmark. Reproduced by Virginia Tech Sanghani Center + Washington Post.
- **Paperclip plugin:** `@vectorize-io/hindsight-paperclip` v0.2.1, npm, published 2026-04-15 (two days before this note). Depends on `@paperclipai/plugin-sdk ^2026.403.0`.
- **Claim:** «eliminates shortcomings of RAG and knowledge graph» for agent memory.
- **Mechanism:** LLM wrapper (2 lines of code) or REST/SDK API. Memories stored + retrieved automatically around LLM calls.
- **Focus:** agent **learning** (lessons extracted), not just recall. Explicit differentiation from our approach.
- **Deployment:** Docker (port 8888 API, 9999 UI). Requires LLM API key (OpenAI shown in README quickstart — presumably Anthropic also works).
- **Plugin README:** 404 at `/hindsight-integrations/paperclip-plugin/README.md` — not in expected subdir, need to look deeper.
- **In use at Fortune 500 + AI startups.**

## palace-memory (ours — GIM-23, GIM-34, GIM-37)

- **Scope:** paperclip history (issues/comments/agents) → plain Neo4j → MCP tools (`palace.memory.lookup`, `palace.memory.health`).
- **Storage:** plain Neo4j 5.26 on existing compose stack, no embeddings, no LLM extraction.
- **Query:** structured filters per-entity, Cypher `MATCH (n:Issue) WHERE … ORDER BY source_updated_at`. No similarity.
- **Maturity:** MVP landed 2026-04-17 08:38 UTC. 37 unit tests. 1 day old.
- **Purpose as designed:** external MCP clients query project history. Not for agent-runtime memory.
- **Roadmap ahead:** N+1 Graphiti service (migration slice), N+2 GitHub extractor, N+3 chat transcripts.

## Direct overlap vs orthogonal use cases

| Use case | Hindsight | palace-memory |
|---|---|---|
| Agent remembers past runs during new run (recall before heartbeat) | ✅ primary | ❌ not designed |
| External AI reads structured project history | ❌ not primary focus | ✅ primary |
| Free-text semantic search on code / docs / history | ✅ (via learning) | ❌ (N+2+ roadmap) |
| Learning lessons across sessions | ✅ SOTA | ❌ not designed |
| Typed filters (status, assignee, time window) | unknown — docs-dependent | ✅ |
| Real-time external MCP tool surface | unknown — plugin exposes commands to agents | ✅ |

**Overlap is less direct than feared.** Hindsight is for agents-recalling-themselves. palace-memory is for external-AI-reading-project. Two different consumers.

## Decision frames

### Frame 1 — Orthogonal, run both

Keep palace-memory (external AI read surface) as-is. Install Hindsight plugin alongside — Gimle agents gain episodic memory without touching our stack. Two systems live in parallel.

- **Pros:** zero re-architecture. Each system optimizes for its consumer.
- **Cons:** Two memory truths; agents know things external AI doesn't; duplicate maintenance.
- **Effort:** ~30 min (install hindsight plugin via our own GIM-38 pattern).

### Frame 2 — Replace palace-memory roadmap with Hindsight-backed MCP tool

Drop the N+1/N+2 palace-memory slices. Write a thin MCP tool (`palace.memory.query` → Hindsight API call) that external clients use. Hindsight does the heavy lifting.

- **Pros:** Hindsight is SOTA and peer-reviewed; we don't reinvent. Simpler long-term.
- **Cons:** Lock-in to Vectorize (company risk); Docker service + LLM API key cost; need to understand Hindsight query API; may not fit structured-filter use case (paperclip wants `status=done`, Hindsight is semantic).
- **Effort:** unknown — depends on whether Hindsight supports structured queries natively.

### Frame 3 — Focused deep research before deciding

Spend 1-2 hours reading Hindsight docs + paper + trying install. Generate a proper GIM-issue comparison report. Decide Frame 1 vs 2 with evidence.

- **Pros:** Informed decision before architectural commitment.
- **Cons:** Delay; costs research time; paperclip agent burn.

## My recommendation — Frame 3 lite

Install `@vectorize-io/hindsight-paperclip` plugin like we did with TG (operational, Board-driven, not through team — 30 min). Let it run alongside palace-memory for a week. See:

1. Does it actually improve agent behaviour (fewer repeat mistakes, better handoff context)?
2. What does its query API look like? Is there overlap with palace.memory.lookup?
3. Does it charge LLM tokens per recall (adds to our burn)?

With live data, Frame 1 vs 2 decision becomes concrete.

**Do NOT sink time into N+1 Graphiti migration slice until this experiment runs.** The Graphiti migration was designed before we knew Hindsight existed. It might be wasted work.

## Open questions

1. Does Hindsight plugin work with `ANTHROPIC_API_KEY` (not just OpenAI as shown in README quickstart)?
2. Per-recall token cost — Hindsight uses LLM for indexing AND retrieval. How much $ per 1000 recalls?
3. MCP surface — does Hindsight expose an MCP-compatible query endpoint, or only the wrapper + plugin commands?
4. Data locality — where do memories live? Hindsight container on iMac, or Vectorize cloud?
5. Privacy — Hindsight enterprise F500 use suggests on-prem deploy works, but confirm no telemetry leaks.

## Next step options for Board

- **A.** Install hindsight plugin now (30 min), observe 1 week, then decide.
- **B.** Create GIM-48 research issue for team to do Frame 3 properly.
- **C.** Defer — finish GIM-44 and N+1 Graphiti brainstorm as planned, revisit hindsight later.
