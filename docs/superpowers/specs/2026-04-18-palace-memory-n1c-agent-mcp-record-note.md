# Palace Memory — N+1c Agent MCP + record_note + provider UX

**Date:** 2026-04-18 (revision 2 — post extended verification)
**Slice:** N+1c (third of three N+1 sub-slices)
**Author:** Board
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §4.2, §4.3; `docs/research/graphiti-core-verification.md` §5.B (mcp_server is separate subproject), §5.E-I (SearchFilters, search_ recipes, namespace API), §5.J (dim-mismatch detection)
**Predecessor slices:** N+1a, N+1b
**Closes:** N+1 palace.memory.* substrate epic

## 1. Context

N+1a substrate + N+1b multi-project complete. This slice closes the epic:

1. **Agent MCP surface** on :8002 (in-process palace-mcp, not separate container) — paperclip agents gain direct graphiti-style tools scoped by per-agent `allowed_group_ids`.
2. **`record_note` + `search`** — first real write/read tools for both external clients and agents.
3. **Provider UX** via `just setup` prompt + `just reset-embeddings` CLI + dim-mismatch detection.
4. **Deploy automation** with HMAC signature + healthcheck rollback.

**Key architectural locks from verification:**
- No `zepai/graphiti` MCP container. palace-mcp hosts both FastMCP apps in one process (:8080 external, :8002 agent) with different middleware stacks.
- Per-agent token → `allowed_group_ids` map from day one (not followup).
- Native `graphiti.search_(config=NODE_HYBRID_SEARCH_RRF)` for search — no hand-rolled `node_similarity_search` wrapping.
- `graphiti.nodes.entity.save(note_node)` with `labels=["Note"]` for record_note.
- HMAC-SHA256 webhook signature + healthcheck-based rollback (not plain shared secret).

## 2. Goal

After this slice:

- Paperclip agents connect to `http://palace-mcp:8002/mcp` with their token → middleware validates `allowed_group_ids` → agent sees graphiti-style tools scoped to allowed projects.
- External clients call `palace.memory.record_note(...)` → creates `:Note:Entity` node with auto-embedded text via native graphiti.
- `palace.memory.search(query, project, top_k)` returns similarity-ranked hits over `:Issue`/`:Comment`/`:Note` via `graphiti.search_(config=NODE_HYBRID_SEARCH_RRF, search_filter=SearchFilters(node_labels=[...]))`.
- `just setup` prompts for provider choice; `just reset-embeddings <project>` rebuilds embeddings after provider swap.
- Merging to develop triggers automated iMac deploy with auto-rollback if health degrades.

**Success criterion:** Claude Code records a note; fresh session `search(query="...", project="gimle")` finds it with score above `SEARCH_MIN_SCORE`. Paperclip CodeReviewer (with its token + `allowed_group_ids=["project/gimle"]`) calls `search_nodes(group_ids=["project/gimle"])` and finds same note; same agent attempting `group_ids=["project/medic"]` gets 403. Trivial docs-only PR merges to develop → deploy listener pulls + rebuilds + ups within 60s; simulated broken PR triggers healthcheck-based rollback to prev SHA.

## 3. Architecture

### 3.1 Single palace-mcp process, two FastMCP apps

```python
# services/palace-mcp/src/palace_mcp/main.py
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

app = FastAPI()

# External curated app on :8080
external_mcp = FastMCP("palace-memory")
external_mcp.tool()(palace_memory_lookup)
external_mcp.tool()(palace_memory_search)
external_mcp.tool()(palace_memory_health)
external_mcp.tool()(palace_memory_record_note)
external_mcp.tool()(palace_memory_list_projects)
external_mcp.tool()(palace_memory_register_project)
# etc.
app.mount("/mcp", external_mcp.streamable_http_app())

# Agent raw app on :8002 — same process, different port via second uvicorn binding
agent_mcp = FastMCP("graphiti-agent")
agent_mcp.tool()(graphiti_add_triplet)            # thin passthrough
agent_mcp.tool()(graphiti_search_nodes)
agent_mcp.tool()(graphiti_search_facts)
agent_mcp.tool()(graphiti_get_by_uuid)
agent_mcp.tool()(graphiti_get_between_nodes)

agent_app = FastAPI()
agent_app.middleware("http")(agent_token_auth)   # X-Agent-Token + allowed_group_ids
agent_app.mount("/mcp", agent_mcp.streamable_http_app())
```

Compose runs palace-mcp with two uvicorn workers (or single worker binding both ports via `uvicorn.Server(...)` multi-config). No separate container, no reverse-proxy.

### 3.2 Auth middleware

```python
# Per-agent token → {agent_id, allowed_group_ids}
# Loaded from .palace/agent-token-map.yaml (gitignored):
# - token: "tok_<32hex>"
#   agent_id: "codereviewer"
#   allowed_group_ids: ["project/gimle"]

@agent_app.middleware("http")
async def agent_token_auth(request, call_next):
    token = request.headers.get("X-Agent-Token")
    token_map = load_token_map()   # cached with TTL 60s
    if not token or token not in token_map:
        return JSONResponse(status_code=401, content={"error": "invalid_agent_token"})

    entry = token_map[token]
    # Attach to request for tool handlers to enforce group_id scoping
    request.state.agent_id = entry["agent_id"]
    request.state.allowed_group_ids = entry["allowed_group_ids"]
    return await call_next(request)

# In each agent tool handler:
def check_group_ids_allowed(request, requested_group_ids: list[str]):
    allowed = set(request.state.allowed_group_ids)
    disallowed = [g for g in requested_group_ids if g not in allowed]
    if disallowed:
        raise HTTPException(403, f"agent_not_allowed_for_group_ids: {disallowed}")
```

### 3.3 Compose delta

```yaml
palace-mcp:
  ports:
    - "8080:8080"   # existing external
    - "8002:8002"   # NEW — agent MCP
  environment:
    # existing + N+1b
    AGENT_TOKEN_MAP_PATH: "/secrets/agent-token-map.yaml"
  volumes:
    - type: bind
      source: ${PWD}/.palace/agent-token-map.yaml
      target: /secrets/agent-token-map.yaml
      read_only: true

ollama-local:
  # NEW — opt-in only
  image: ollama/ollama:0.5.0
  profiles: [with-local-ollama]
  mem_limit: 4g
  # ... as in revision 1

palace-deploy-listener:
  # NEW — post-merge deploy automation
  build: services/deploy-listener
  profiles: [full]
  restart: unless-stopped
  environment:
    DEPLOY_HMAC_SECRET: "${DEPLOY_HMAC_SECRET}"    # used to verify GitHub webhook signature
    COMPOSE_DIR: "/compose"
    BRANCH: "develop"
    HEALTH_URL: "http://palace-mcp:8080/healthz"
  volumes:
    - /Users/Shared/Ios/Gimle-Palace:/compose
    - /var/run/docker.sock:/var/run/docker.sock
  ports:
    - "9090:9090"
```

## 4. Schema additions

### 4.1 `:Note` entity

```python
note_node = EntityNode(
    uuid=str(uuid4()),
    name=f"note-{uuid[:8]}",
    labels=["Note"],                           # :Entity auto-prepended
    group_id=f"project/{project_slug}",
    summary=text[:500],
    attributes={
        "text": text,
        "tags": tags,
        "scope": scope,
        "author_kind": author_kind,
        "author_id": author_id,
        "source_created_at": now_iso(),
        "palace_last_seen_at": now_iso(),
        "text_hash": sha256(text.encode()).hexdigest(),
    }
)
await graphiti.nodes.entity.save(note_node)
```

No inbound/outbound edges by default. `palace.memory.link_items` creates typed edges separately if needed.

### 4.2 Dedup

```python
# Before save, check for near-identical existing note
results = await graphiti.search_(
    query=text[:200],
    config=NODE_HYBRID_SEARCH_RRF.model_copy(deep=True, update={"limit": 5}),
    search_filter=SearchFilters(node_labels=["Note"]),
    group_ids=[f"project/{project_slug}"],
)

DEDUP_MIN_SCORE = float(os.getenv("DEDUP_MIN_SCORE", "0.95"))
if results.nodes:
    best = max(results.nodes, key=lambda n: n.score)
    if best.score >= DEDUP_MIN_SCORE:
        return {"note_id": best.uuid, "deduplicated": True, "score": best.score}
# else proceed with save
```

## 5. MCP tool surface — 3 new on external, raw-API passthroughs on agent

### 5.1 External palace-memory tools (3 new + inherited)

| Tool | Behavior |
|---|---|
| `palace.memory.record_note(text, tags, scope, project, author_id)` | Build `:Note` EntityNode; dedup via `search_`; `graphiti.nodes.entity.save` triggers embed. Return `{note_id, deduplicated: bool}`. |
| `palace.memory.search(query, project, labels_filter, top_k)` | `graphiti.search_(config=NODE_HYBRID_SEARCH_RRF, search_filter=SearchFilters(node_labels=[labels_filter or default]), group_ids=resolve_group_ids(project))`. Default labels: `["Issue", "Comment", "Note"]`. Returns `list[SearchHit]` with score + project + labels. |
| `palace.memory.link_items(from_id, to_id, relation, project)` | Whitelisted relations: `RELATES_TO`, `SIMILAR_TO`, `SEE_ALSO`, `DEPRECATES`. Build EntityEdge; `graphiti.edges.entity.save`. |

Thresholds via env:
- `DEDUP_MIN_SCORE` (default 0.95) — near-identical dedup threshold
- `SEARCH_MIN_SCORE` (default 0.4) — minimum similarity for returned hits

Acceptance tests reference "score above threshold" not literal numbers.

### 5.2 Agent graphiti tools on :8002 (raw passthroughs)

| Tool | Behavior |
|---|---|
| `graphiti_search_nodes(query, group_ids, labels, limit)` | Thin wrapper calling `graphiti.search_(config=NODE_HYBRID_SEARCH_RRF, ...)` after `check_group_ids_allowed(request, group_ids)`. |
| `graphiti_search_facts(query, group_ids, limit)` | Uses `EDGE_HYBRID_SEARCH_CROSS_ENCODER`. |
| `graphiti_get_by_uuid(uuid)` | `graphiti.nodes.entity.get_by_uuid(uuid)` + group_id check post-fetch. |
| `graphiti_get_between_nodes(source_uuid, target_uuid)` | `graphiti.edges.entity.get_between_nodes(...)` + group_id check. |
| `graphiti_add_triplet(source, edge, target)` | Writes through graphiti API; enforces `group_id ∈ allowed_group_ids` on source+edge+target before write. |

**Guidance in shared-fragments:** agents should prefer `palace.memory.record_note` on :8080 (curated, typed :Note) over raw `graphiti_add_triplet` for note-like writes. Raw triplet reserved for advanced graph operations.

## 6. Provider UX

### 6.1 `just setup` interactive prompt

```
Q1: Embedding provider?
  1) External Ollama (your hosted instance — default, fast path for current deploy)
  2) Cloud OpenAI-compatible (Alibaba DashScope free tier / OpenAI / Voyage)
  3) Local Ollama compose service (opt-in profile `with-local-ollama`; needs 4GB RAM)

[User picks 2 → Alibaba DashScope]
Q2: EMBEDDING_BASE_URL? [default: https://dashscope-intl.aliyuncs.com/compatible-mode/v1]
Q3: EMBEDDING_API_KEY? (stored in .env, not committed) > sk-...
Q4: EMBEDDING_MODEL? [default: text-embedding-v3]
Q5: EMBEDDING_DIM? [default: 1024 for text-embedding-v3]

Q6: Generate agent tokens now? (one per live paperclip agent — 11 total)
  1) Generate 11 random tokens (written to .env + .palace/agent-token-map.yaml, both gitignored)
  2) Provide existing list

Q7: Enable GitHub-Actions-triggered post-merge deploy?
  1) Yes (requires DEPLOY_HMAC_SECRET env + workflow file)
  2) Skip — manual deploy only
```

### 6.2 `just reset-embeddings [<project-slug>]`

```bash
just reset-embeddings gimle
# → deletes all entity-node embeddings in group_id=project/gimle
# → re-runs ingest which regenerates embeddings with new provider
# → updates :Project.provider_config_hash
```

Needed when embedding provider changes (e.g., Ollama nomic-768 → Alibaba text-embedding-v3-1024).

### 6.3 Dim-mismatch detection

Each `:Project` node stores `provider_config_hash = sha256(f"{EMBEDDING_MODEL}:{EMBEDDING_DIM}")[:16]`. Current env computes same at startup. Mismatch → `palace.memory.health()` response `provider_config_hash_mismatches: ["gimle"]` + warning in logs `{"event":"health.provider.mismatch","slug":"gimle"}`.

## 7. Post-merge deploy automation

### 7.1 Listener service

```python
# services/deploy-listener/main.py
@app.post("/deploy")
async def deploy(request: Request, x_hub_signature_256: str = Header(...)):
    body = await request.body()
    expected = "sha256=" + hmac.new(
        DEPLOY_HMAC_SECRET.encode(), body, "sha256"
    ).hexdigest()
    if not hmac.compare_digest(x_hub_signature_256, expected):
        raise HTTPException(401, "invalid_signature")

    payload = json.loads(body)
    if payload["ref"] != "refs/heads/develop":
        return {"skipped": f"ref {payload['ref']} not develop"}

    # Capture current SHA for potential rollback
    prev_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=COMPOSE_DIR
    ).decode().strip()

    # Pull + rebuild + up
    subprocess.run(["git", "pull"], cwd=COMPOSE_DIR, check=True)
    subprocess.run(["docker", "compose", "pull"], cwd=COMPOSE_DIR, check=True)
    subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=COMPOSE_DIR, check=True)

    # Healthcheck-based auto-rollback
    await asyncio.sleep(30)   # grace for services
    for attempt in range(3):
        try:
            r = httpx.get(HEALTH_URL, timeout=5)
            if r.status_code == 200:
                return {"deployed": payload["after"]}
        except Exception:
            pass
        await asyncio.sleep(10)

    # Health failed — rollback
    subprocess.run(["git", "checkout", prev_sha], cwd=COMPOSE_DIR, check=True)
    subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=COMPOSE_DIR, check=True)
    return {"rolled_back": prev_sha, "failed_sha": payload["after"]}
```

### 7.2 GitHub Actions workflow

```yaml
# .github/workflows/deploy-on-merge.yml
name: Deploy on merge to develop
on:
  push:
    branches: [develop]
jobs:
  trigger-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Notify iMac listener
        env:
          DEPLOY_HMAC_SECRET: ${{ secrets.DEPLOY_HMAC_SECRET }}
          PAYLOAD: ${{ toJson(github.event) }}
        run: |
          SIG="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$DEPLOY_HMAC_SECRET" -hex | cut -d' ' -f2)"
          curl -X POST https://palace.ant013.work/deploy \
            -H "X-Hub-Signature-256: $SIG" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD"
```

### 7.3 Failure-mode coverage

Acceptance test: push a known-broken commit to a throwaway branch, rebase into develop via PR, merge → listener pulls → healthcheck fails → auto-rollback → verify `palace.memory.health()` returns prev SHA.

## 8. Shared-fragments update

New fragment `paperclip-shared-fragments/fragments/palace-memory-mcp.md`:

```markdown
## Palace Memory MCP access

Two MCP servers:

1. **palace-memory** (curated tools; preferred for writes and typical reads)
   - URL: http://palace-mcp:8080/mcp (Docker internal)
   - Writes: palace.memory.record_note(text, tags, scope, project)
   - Search: palace.memory.search(query, project)
   - Structured: palace.memory.lookup(entity_type, filters, project)

2. **graphiti** (raw graph access for advanced read/traversal)
   - URL: http://palace-mcp:8002/mcp (Docker internal, same process as palace-memory)
   - Auth: header X-Agent-Token: <YOUR_TOKEN> (provided via GIMLE_AGENT_TOKEN env)
   - Tools: graphiti_search_nodes, graphiti_search_facts, graphiti_get_by_uuid, graphiti_get_between_nodes, graphiti_add_triplet
   - Scope: your token allows specific group_ids; passing group_ids outside your allowance returns 403.

**Default project for agents:** "gimle" (or your current project slug).
**When to use raw graphiti vs curated palace.memory:** prefer palace.memory. Only drop to graphiti for advanced graph traversal the curated tools don't expose.
```

## 9. Decomposition (plan-first ready)

Expected plan-file: `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1c-agent-mcp.md`.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create issue + plan. |
| 1 | 1.2 | CodeReviewer | Plan-first; verify N+1b green. APPROVE. |
| 2 | 2.1 | MCPEngineer | Expose second FastMCP app on :8002 same process; auth middleware with token-map yaml loader + group_id enforcement. |
| 2 | 2.2 | MCPEngineer | Implement `palace.memory.record_note` + dedup + :Note node build. |
| 2 | 2.3 | MCPEngineer | Implement `palace.memory.search` via `graphiti.search_(NODE_HYBRID_SEARCH_RRF)` with SearchFilters label pushdown + env thresholds. |
| 2 | 2.4 | MCPEngineer | Implement `palace.memory.link_items` with whitelisted relations via `graphiti.edges.entity.save`. |
| 2 | 2.5 | MCPEngineer | Implement raw agent tools on :8002 (graphiti_search_nodes, search_facts, get_by_uuid, get_between_nodes, add_triplet) with `check_group_ids_allowed` guard. |
| 2 | 2.6 | MCPEngineer | `ollama-local` compose service under `with-local-ollama` profile + auto-pull init. |
| 2 | 2.7 | MCPEngineer | `just setup` interactive prompt; token-map + agent-token-map.yaml generation; .gitignore entries. |
| 2 | 2.8 | MCPEngineer | `just reset-embeddings <project>` CLI; dim-mismatch detection in health. |
| 2 | 2.9 | MCPEngineer | `services/deploy-listener/` — HMAC verification + healthcheck-rollback flow; Dockerfile; `.github/workflows/deploy-on-merge.yml`. |
| 2 | 2.10 | MCPEngineer | Shared-fragments PR: `palace-memory-mcp.md` fragment. |
| 2 | 2.11 | MCPEngineer | Unit tests — record_note dedup, search min_score, auth middleware (401/403 cases), group_id enforcement, HMAC signature verification, rollback flow (mocked docker calls), dim-mismatch detection (≥60 new tests). |
| 3 | 3.1 | CodeReviewer | PR mechanical: compliance, auth 401/403 enforced, HMAC constant-time compare, deploy listener does not execute commits without valid signature, no raw Cypher, mypy --strict. |
| 3 | 3.2 | OpusArchitectReviewer | (If wired) context7 cross-check on graphiti.search_ recipe usage, FastMCP multi-app pattern, FastAPI HMAC middleware. |
| 4 | 4.1 | QAEngineer | Full smoke (6 scenarios): (a) external record_note → restart → search finds it above threshold; (b) paperclip CodeReviewer via :8002 with token finds same note via search_nodes; (c) same agent passing disallowed group_ids → 403; (d) invalid token → 401; (e) trivial docs PR merged to develop → listener deploys + health green → SHA updated; (f) intentionally broken PR merged → listener deploys → healthcheck fails → auto-rollback to prev SHA → health returns prev SHA. |
| 4 | 4.2 | MCPEngineer | Squash-merge. Update checkboxes. Close N+1 epic. |

## 10. Acceptance criteria

- [ ] PR against develop; squash-merged on APPROVE.
- [ ] palace-mcp exposes :8002 graphiti-agent surface in same process as :8080; no separate container.
- [ ] X-Agent-Token auth: invalid/missing → 401.
- [ ] group_id enforcement: token with `allowed_group_ids=["project/gimle"]` requesting `group_ids=["project/medic"]` → 403.
- [ ] `palace.memory.record_note(text="Coordinator pattern used in Gimle bootstrap", tags=["pattern"], project="gimle")` → `:Note:Entity` node created; returned `note_id` retrievable via `palace.memory.lookup(entity_type="Note", project="gimle")`.
- [ ] Dedup: calling `record_note` twice with identical text returns same `note_id` second call with `deduplicated: true` + score above `DEDUP_MIN_SCORE`.
- [ ] `palace.memory.search(query="Coordinator pattern", project="gimle")` returns the note with score above `SEARCH_MIN_SCORE`.
- [ ] `palace.memory.link_items(from_id, to_id, "RELATES_TO", "gimle")` creates edge; non-whitelisted relation → `ok: false`.
- [ ] `just setup` interactive prompt runs; 3 provider choices; agent-tokens → `.env` + `.palace/agent-token-map.yaml` (both gitignored; verified via `git status`).
- [ ] `ollama-local` compose service only brought up with explicit `COMPOSE_PROFILES=full,with-local-ollama`.
- [ ] Shared-fragments `palace-memory-mcp.md` fragment deployed to all 11 agents via `deploy-agents.sh`; each agent env has its own `GIMLE_AGENT_TOKEN`.
- [ ] `just reset-embeddings gimle` deletes + re-ingests embeddings; `provider_config_hash` updated.
- [ ] `palace.memory.health()` `provider_config_hash_mismatches: ["gimle"]` appears when running with env different from stored.
- [ ] HMAC-SHA256 webhook signature verified; invalid signature → 401; no git/docker commands executed.
- [ ] Auto-rollback: trivial broken commit simulates health failure → listener reverts to prev SHA; next health check green; audit log at `/var/log/palace-deploy.log` documents rollback.
- [ ] End-to-end: record → restart → search; external + agent paths both green.
- [ ] `uv run mypy --strict` green across palace-mcp + deploy-listener.
- [ ] CI green.
- [ ] Post-merge (automatic via new mechanism): user verifies all N+1c features from fresh Claude Code session; paperclip agent writes a test note via record_note during a task.

## 11. Out of scope

- **Per-project auth tokens** (different token per project). Per-agent tokens with `allowed_group_ids` is the MVP model.
- **`:Note` edge invalidation / temporal expiry.** All Note edges (created via link_items) are permanent until manually deprecated. Invalidation lands when use case emerges (deprecated note, superseded link).
- **Hybrid BM25+vector+graph-expansion search.** Pure RRF hybrid via NODE_HYBRID_SEARCH_RRF recipe in N+1c. Custom composite recipes come later.
- **Agent write via raw `graphiti_add_triplet` as primary path.** Curated `palace.memory.record_note` is the discouraged-override model documented in shared-fragments.
- **Scheduled ingest.** Manual trigger only.
- **Token rotation automation.** Static tokens in env; rotation is followup.
- **mTLS on :8002.** Plain HTTP over Docker internal network; hardening is followup.
- **Deploy listener exposed externally with full TLS stack.** Listener on ingress domain already (palace.ant013.work); TLS cert via LetsEncrypt assumed pre-existing (same as palace-mcp external reach).
- **Dim-mismatch auto-repair.** Warning only; user runs `just reset-embeddings` manually.

## 12. Estimated size

- Code: ~650 LOC (second FastMCP app + middleware ~150, record_note + dedup ~80, search wrapping search_ ~60, link_items ~40, agent raw tools + guards ~120, ollama-local + init ~40, installer rewrite ~120, deploy-listener ~100, tests ~150).
- Plan + docs: ~80 LOC.
- Shared-fragments PR: separate, ~30 LOC.
- 2 PRs (main + shared-fragments), 4-5 handoffs main.
- Duration: 3 days agent-time.

## 13. Followups

- N+2 brainstorm unblocked immediately; `docs/research/extractor-library/report.md` §8 roadmap is the blueprint.
- Token rotation automation when manual refresh becomes painful.
- Evaluate URL-scoping path (Path B from N+1b followup) once 2+ live projects exist.
- Dim-mismatch auto-repair when second provider swap happens.
- Close `reference_post_merge_deploy_gap.md` memory entry after 1 week of stable auto-deploy.
