# Infra Engineer — Research Notes

**Research date:** 2026-04-15
**Purpose:** inform `templates/engineers/infra-engineer.md` in paperclip-shared-fragments
**Target deployment:** Gimle-Palace InfraEngineer role (Docker Compose profiles + Justfile + installer + Neo4j/Graphiti/palace-mcp/telemetry/scheduler/cloudflared single-node stack)

## 1. Sources reviewed

| Source | Type | Credibility | Key file |
|---|---|---|---|
| voltagent-subagents/devops-engineer | community plugin | VoltAgent marketplace | `devops-engineer.md` (286 lines) |
| voltagent-subagents/docker-expert | community plugin | VoltAgent marketplace | `docker-expert.md` (278 lines) |
| voltagent-subagents/platform-engineer | community plugin (opus) | VoltAgent marketplace | `platform-engineer.md` (286 lines) |
| voltagent-subagents/sre-engineer | community plugin | VoltAgent marketplace | `sre-engineer.md` (286 lines) |
| voltagent-subagents/deployment-engineer | community plugin | VoltAgent marketplace | `deployment-engineer.md` (286 lines) |
| voltagent-subagents/terraform-engineer | community plugin | VoltAgent marketplace | `terraform-engineer.md` |
| voltagent-subagents/kubernetes-specialist | community plugin | VoltAgent marketplace | `kubernetes-specialist.md` |
| claude-agents/cloud-infrastructure/cloud-architect | agent (opus) | wshobson-style 2024/25 | `cloud-architect.md` |
| claude-agents/cloud-infrastructure/deployment-engineer | agent (haiku) | wshobson-style | `deployment-engineer.md` |
| claude-agents/cicd-automation/devops-troubleshooter | agent (sonnet) | wshobson-style | `devops-troubleshooter.md` |
| claude-agents/observability-monitoring/observability-engineer | agent | wshobson-style, 2024/25 | `observability-engineer.md` |
| claude-agents/kubernetes-operations/kubernetes-architect | agent | wshobson-style | `kubernetes-architect.md` |
| Medic paperclips/backend-engineer.md | field-tested role (in-prod) | author's previous template | `backend-engineer.md` (46 lines) |
| Last9 — Docker Compose healthcheck guide 2026 | blog | — | web |
| Nick Janetakis — production-ready Docker Compose | blog (widely-cited) | — | web |
| freecodecamp — Compose profiles/watch/GPU 2025 | article | — | web |
| OneUptime — Docker healthcheck best practices 2026-01 | blog | — | web |
| just.systems manual + GitHub casey/just | official docs + repo (~20k stars) | primary | web |
| 12factor.net `/config` + itnext "15 years later" 2026 review | seminal + retrospective | primary | web |
| getsops/sops README + GitGuardian SOPS guide + cmmx.de 2025 age+sops | GitHub + blog | primary | web |
| peter-evans/docker-compose-healthcheck | reference repo | — | web |

11 primary role/plugin prompts + Medic template + 8 web articles/official docs = strong signal.

## 2. Common structural patterns

Section frequency across the 5 core infrastructure community prompts (voltagent devops/docker/platform/sre/deployment):

| Section | Count | Notes |
|---|---|---|
| Role / Purpose statement (1-2 lines, seniority framing) | 5/5 | Universal |
| "When invoked" 4-step trigger list | 5/5 | voltagent-style only |
| Domain-specific excellence checklist (%-targets, SLO numbers) | 5/5 | Universal; numeric targets ("availability > 99.9%", "MTTR < 30 min") |
| Capability taxonomy (IaC, containers, CI/CD, security, observability, cost) | 5/5 | Flat "Area: bullets" blocks |
| Communication Protocol / JSON context query | 5/5 | voltagent-only — adds ~15 lines of overhead, low signal for our use case |
| Development Workflow — Assessment / Implementation / Excellence phases | 5/5 | voltagent pattern |
| Progress tracking JSON snippet | 5/5 | voltagent-only |
| "Integration with other agents" | 5/5 | Cross-agent delegation list |
| Behavioral traits block | 3/5 | claude-agents + platform-engineer |
| Example interactions | 3/5 | claude-agents only |
| Knowledge base / stack enumeration | 4/5 | claude-agents emphasise tool lists |

claude-agents counterparts (cloud-architect, deployment-engineer, observability-engineer) are **capability dumps** — 150-230 lines, heavy on tool enumeration (every cloud provider, every observability vendor). Useful as a content-rule catalogue, wasteful as a structural template.

Medic `backend-engineer.md` (46 lines) uses a much tighter shape:
- Role (1-2 lines, "only role-specific, invariants in CLAUDE.md")
- Responsibility table (path map)
- Pre-work checklist (load-bearing invariants)
- MCP / Subagents / Skills (single line each)
- `@include` fragments (pre-work-discovery, git-workflow, worktree-discipline, heartbeat, language)

**Divergence:** community infra prompts are 250-300 line capability dumps with multi-cloud scope; Medic's are ~45-line operational role-cards pinned to one concrete stack. Our template must follow Medic's shape (per Gimle-Palace spec §4.1 ≤2000 token budget) and **use** community prompts only as a rule catalogue. Gimle-Palace is explicitly "docker-compose + Justfile + single-node, no K8s/Ansible/Helm in MVP" (spec §3.4, §15) — so multi-cloud / K8s content is out-of-scope noise.

## 3. Canonical content rules (aggregate consensus)

Top rules appearing in 3+ sources (ranked by signal × Gimle-Palace relevance):

1. **Everything in code / IaC — no clicking, no manual steps** — 9/11 sources. For Gimle-Palace: docker-compose.yml + Justfile + installer are the only entry points; any change reproducible from repo checkout.
2. **Healthchecks for every service, with `start_period` + `depends_on: condition: service_healthy`** — 5/5 voltagent infra prompts + 5/5 web sources. Neo4j: `cypher-shell RETURN 1`, Postgres: `pg_isready`, FastAPI: `curl -f /health`, long-boot services need generous `start_period` (Neo4j warmup often > 30s).
3. **Multi-stage Dockerfiles + minimal/distroless base + non-root user + `.dockerignore`** — 4/4 Docker-focused sources. Image size, vuln surface, build cache hit > 80%.
4. **Restart policies (`unless-stopped` for daemons, `on-failure` for jobs), resource limits (`mem_limit`, `cpus`)** — 4/5 production-Compose sources. Prevents OOM cascades.
5. **Named volumes for persistent data; never host bind-mounts for databases in prod** — 4/4 Compose production sources. Portability + backup.
6. **Secrets via env vars (12-factor) OR sops-encrypted files; NEVER hard-coded, NEVER committed unencrypted** — 12factor + 4/4 sops sources + all voltagent prompts. `.env` gitignored; `.env.example` with placeholders committed; optional `.env.sops.yaml` with age keys for team distribution.
7. **Compose profiles for environment variants (dev/review/analyze/full), NOT separate compose files duplicated** — freecodecamp 2025 + Last9. Single source of truth; `COMPOSE_PROFILES` env drives activation. Directly mirrors Gimle-Palace spec §3.5 profile design.
8. **Justfile as the single task entry point with self-documenting recipes (`# comment above recipe` shows in `just --list`)** — just.systems manual + 3 blog sources. `just setup`, `just up`, `just down`, `just backup`, `just logs`, `just test`.
9. **Structured logging + centralised aggregation + health/metrics endpoints + OpenTelemetry trace correlation** — 5/5 observability + SRE sources. FastAPI telemetry service is the aggregation point in Gimle-Palace.
10. **Pinned image digests (`image: neo4j:5.26.0@sha256:...`) or at minimum explicit tags; never `:latest` in prod** — 4/4 Docker sources. Supply-chain predictability.
11. **SLI/SLO + error budget discipline; MTTR + deployment-frequency + change-failure-rate tracked (DORA metrics)** — 5/5 SRE + deployment sources.
12. **Backup automation with retention tiers (hourly/daily/weekly) + tested restore paths** — voltagent SRE + Gimle spec §3.7.
13. **`install-server.sh` / bootstrap script idempotent; re-run detects existing state, offers update/preserve options** — platform-engineer + deployment-engineer emphasise idempotency.
14. **Network isolation: purpose-scoped shared network (`paperclip-agent-net`), not default bridge; service-to-service via service name** — Docker/Compose canonical.
15. **CI validates compose file (`docker compose config`), lints Dockerfile (`hadolint`), scans images (`trivy`/Scout) on every push** — 4/5 CI sources.

## 4. Tooling recommendations

### MCP servers (pre-wire for Infra role)

- **serena** — semantic nav for Justfile, shell scripts, compose yaml (fallback to Read/Edit/Grep since YAML support is limited)
- **context7** — Docker Compose / Docker engine / Neo4j / Graphiti / FastAPI / sops / just docs (training-data lag is real here — healthcheck v3.x spec changes, Compose profile syntax)
- **filesystem** — for reading `.env`, cert files, shell scripts
- **github** — CI/CD workflow editing, issues, PRs
- **sequential-thinking** — complex multi-profile dependency graphs, installer state machine
- **bash** (via direct tool, not MCP) — `docker compose`, `just`, `curl` probes — **explicit allowlist** because infra role runs destructive ops (stop/rm/prune)

### Subagents invoked as tools

Primary: `devops-engineer`, `docker-expert`, `deployment-engineer` (all voltagent).
Support: `sre-engineer` (healthcheck/SLO design), `observability-engineer` (telemetry FastAPI design), `security-engineer` (sops/age policy, supply-chain scan), `platform-engineer` (installer DX), `devops-troubleshooter` (when compose/network goes sideways).
Out-of-scope for Gimle-Palace MVP (but named for future): `kubernetes-specialist`, `terraform-engineer`, `cloud-architect`, `hybrid-cloud-architect`, `terragrunt-expert`. Note as "add when scope expands beyond single-node".

### Skills

- `superpowers:test-driven-development` — write failing healthcheck/compose-validation test before implementation
- `superpowers:systematic-debugging` — compose boot failures, network partitions, volume permission issues
- `superpowers:verification-before-completion` — `docker compose config` validates, `just setup --yes` green, all healthchecks pass, `just down && just up` idempotent
- `superpowers:receiving-code-review`, `simplify`
- **Gap noted:** no community skill specifically for "Docker Compose anti-patterns" or "Justfile conventions". Inline the 5-7 critical ones in the template body (§5 below).

### External refs (URL only, never paste inline)

- Docker Compose spec: https://docs.docker.com/compose/compose-file/
- Compose profiles: https://docs.docker.com/compose/how-tos/profiles/
- Docker healthcheck: https://docs.docker.com/reference/dockerfile/#healthcheck
- peter-evans/docker-compose-healthcheck: https://github.com/peter-evans/docker-compose-healthcheck
- just manual: https://just.systems/man/en/ — repo: https://github.com/casey/just
- 12factor.net: https://12factor.net/
- sops: https://github.com/getsops/sops — age: https://github.com/FiloSottile/age
- hadolint: https://github.com/hadolint/hadolint — trivy: https://trivy.dev/
- Neo4j Docker docs: https://neo4j.com/docs/operations-manual/current/docker/
- cloudflared tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/

## 5. Anti-patterns / mistakes to call out

Explicit bans the template should surface (signal: 3+ sources OR load-bearing for Gimle-Palace):

- `image: <name>:latest` in production compose — **no reproducibility; silent upgrades break boot**.
- Hard-coded secrets in compose.yml, Dockerfile, or committed `.env` — **use `.env.example` + `.env` (gitignored) + optional `.env.sops.yaml`**.
- No healthcheck, or healthcheck that only returns 200 without checking deps — **cascading boot failures**. Every service needs a real probe; FastAPI telemetry must check Neo4j+Graphiti connectivity in `/health/deep`.
- `depends_on: [db]` without `condition: service_healthy` — **app starts before DB ready, crashes, restart storm**.
- Host bind-mounts for Neo4j/Postgres data in prod (`- ./data/neo4j:/data`) — **permission hell, no portability; use named volumes**.
- Running containers as root (no `USER` in Dockerfile, no `user:` in compose) — **CVE blast radius**.
- Default bridge network with port-mapping everywhere — **use a named `paperclip-agent-net` + expose only public-facing service ports on host**.
- Multiple `docker-compose.dev.yml`, `docker-compose.prod.yml` duplicated files — **use profiles + `docker-compose.override.yml`** (spec §3.4 already does this).
- `docker system prune -a` in Justfile without confirmation guard — **destroys unrelated containers**.
- Justfile recipes without `# comment` — **invisible in `just --list`, undiscoverable**.
- Justfile recipes that `cd` without `set working-directory` or absolute paths — **breaks when called from subdirectory**.
- `sops rotate` skipped when team member leaves — **compromised key still decrypts history**. Policy: rotate on offboarding + quarterly.
- No `start_period` on slow-boot services (Neo4j, Ollama) — **retries exhausted during warmup, container marked unhealthy forever**.
- Installer script not idempotent — **re-run corrupts existing `.env`/volumes**. Detect + prompt per Gimle spec §3.6.
- `curl | sh` installer without checksum verification — **supply-chain risk**; ship SHA256 + signed tag.
- Ignoring restart policy — **one crash kills prod until manual intervention**.
- Logging to stdout only without aggregation — **logs vanish on container restart**; route to telemetry FastAPI or mounted log volume.
- Backup script that doesn't test restore — **silent corruption discovered at worst moment**.

Gimle-Palace specific:
- `paperclip-agent-net` absent or misnamed — **client roles can't reach palace-mcp**; network name is a load-bearing contract (spec §3.1).
- Embedded Paperclip profile + external Paperclip URL both set — **installer must enforce mutual exclusion** (spec §3.6).
- cloudflared running without tunnel auth → **tunnel fails to register; palace-mcp not reachable externally**; auth secret must be in sops or Compose secret, never in compose.yml.

## 6. Recommendations for template

**Structure decision:** mirror Medic's role-card shape (Role, Responsibility table, Checklist, MCP/Subagents/Skills, `@include` fragments). Community 250-300-line prompts blow the token budget and drag in irrelevant K8s/multi-cloud content. Push the 15 canonical rules into a short "Правила" block (7-9 bullets max) and delegate detail to `context7` + anti-patterns list. Put Gimle-Palace-specific section (Compose profiles, paperclip-agent-net, cloudflared, installer idempotency) inline because no external skill covers it.

**Responsibility table (Gimle-Palace-tailored) candidate:**

| Область | Путь |
|---|---|
| Compose stack | `docker-compose.yml`, `docker-compose.paperclip.yml` |
| Profile overrides | `docker-compose.override.yml` (generated by installer) |
| Env contract | `.env.example` (committed), `.env` (gitignored), `.env.sops.yaml` (optional) |
| Task runner | `Justfile` (setup, up, down, logs, backup, test, deploy) |
| Server bootstrap | `install-server.sh` + interactive installer |
| Installer profiles | `installer/profiles/*.yaml` (review/analyze/full/client/custom) |
| Dockerfiles | `services/*/Dockerfile` (multi-stage, non-root, digest-pinned base) |
| Healthchecks | inline in compose.yml per service + `/health` endpoints in palace-mcp + telemetry |
| Networking | `paperclip-agent-net` (shared external network) |
| Cloudflared | `services/cloudflared/` + tunnel credentials in sops |
| Backup | `just backup` + `scripts/backup.sh` + retention config in `.env` |
| CI | `.github/workflows/*.yml` (validate compose, lint, scan) |

**Pre-work checklist (load-bearing invariants):**

- [ ] Затрагивает ли изменение `paperclip-agent-net`? (имя сети — контракт с клиентскими ролями)
- [ ] Есть ли healthcheck для нового сервиса? `start_period` достаточен?
- [ ] Все `depends_on` используют `condition: service_healthy`?
- [ ] Образ запинен на tag + digest? (`@sha256:...`)
- [ ] Секреты только через `.env` / sops — нет hard-coded?
- [ ] Новый сервис попал в правильные `profiles:`? (review/analyze/full)
- [ ] `just setup --yes` на чистой машине проходит идемпотентно?
- [ ] `docker compose config` валидирует без warning?
- [ ] CI добавлен scan (hadolint/trivy) для нового Dockerfile?
- [ ] Обновлён `.env.example` и инсталлер профиль yaml?

**Content bans to include (explicit, short list):**
- no `:latest` tags, no unpinned base images — pin tag + optionally digest
- no hard-coded secrets — `.env` / sops only; `.env.example` with placeholders committed
- no service without healthcheck + real probe (не `exit 0`)
- no `depends_on` без `condition: service_healthy` для data services
- no root containers, no host bind-mounts for DB data (named volumes only)
- no duplicated compose files — profiles only
- no destructive Justfile recipes без confirm guard
- no non-idempotent installer — detect existing state

**Tooling to pre-wire (final list):**
- MCP: `serena`, `context7`, `filesystem`, `github`, `sequential-thinking`
- Subagents: `devops-engineer`, `docker-expert`, `deployment-engineer`, `sre-engineer`, `observability-engineer`, `security-engineer`, `devops-troubleshooter`
- Skills: `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review`, `simplify`

**Verification gate (Medic-style, must-do before done):**
- `docker compose config -q` — валидирует yaml
- `hadolint services/*/Dockerfile` — lint Dockerfile
- `just setup --profile full --yes` на чистой VM — green
- Все healthchecks pass (`docker compose ps` — все `healthy`)
- `just down && just up` — идемпотентно
- `just backup && just restore --dry-run` — работает
- если трогали cloudflared — tunnel register OK, external URL 200

**Tokens budget estimate:** target ≤1500 tokens for role body; after `@include` of standard fragments (pre-work-discovery, git-workflow, worktree-discipline, heartbeat-discipline, language) total ≈1800-2000 tokens. Fits spec §4.1.

## 7. Open questions for user

1. **Dockerfile location convention** — spec §3.4 shows `services/<name>/Dockerfile`; confirmed, or do some services use top-level `Dockerfile.<name>`? Affects responsibility table exact path.
2. **sops adoption level** — MVP or post-MVP? Spec §4.1 mentions "optional sops-encrypted secrets" — do we flag sops as **required** for multi-operator deploys (team install) and **optional** for single-operator (solo)? Template wording depends.
3. **cloudflared scope** — does InfraEngineer own tunnel provisioning end-to-end (create tunnel via `cloudflared` API, install cert, configure routes), or is tunnel pre-created and role only wires it in compose? Affects responsibility + checklist.
4. **Backup tier policy** — is `backup.sh` InfraEngineer's file or shared with DataEngineer? Neo4j dumps vs. Postgres vs. SQLite (Paperclip) each have different tooling.
5. **CI platform** — GitHub Actions only, or also self-hosted runner on install-server? If runner, InfraEngineer also owns runner lifecycle.
6. **Container registry** — build locally + `docker compose build` on the server? Or push to GHCR / Docker Hub and pull? Affects supply-chain checklist (image signing, digest pinning).
7. **Healthcheck for palace-mcp `/health/deep`** — does it check upstream Graphiti + Neo4j + Paperclip connectivity, or is shallow `/health` enough? Error-budget implication: deep checks cause cascading unhealthy states.
8. **Justfile nesting** — single top-level Justfile, or modules (`justfiles/backup.just`, `justfiles/dev.just`)? just.systems recommends splitting "when unwieldy"; pick threshold.
9. **Paperclip-agent-net** — external (pre-created by install-server.sh) or internal (compose-managed)? If external, installer must create; if internal, client roles joining from outside the compose must use `external: true` + same name. Confirm.
10. **Include `installer/` scripts ownership** — does InfraEngineer own `install-server.sh` + installer Python/Bash, or is there a separate "installer-engineer"? If shared, define split (e.g., InfraEngineer owns compose generation, PlatformEngineer owns interactive UX).
