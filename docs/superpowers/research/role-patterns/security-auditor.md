# SecurityAuditor — Research Notes

**Research date:** 2026-04-16
**Purpose:** inform `paperclips/roles/security-auditor.md` (Slice #12)
**Target:** smart orchestrator для security/compliance audits — invokes specialized subagents, не executes сам

## 1. Sources reviewed

| Source | Stars | Length | Signal |
|---|---|---|---|
| **wshobson/agents** | 33.7k | 182 agents | `security-auditor` (OWASP), `threat-modeling-expert` (STRIDE+attack trees), `backend-security-coder`, `frontend-security-coder`. Three-tier model strategy (Opus=critical, Sonnet=coord, Haiku=ops). NO penetration-tester or compliance-auditor — gap |
| **VoltAgent `security-auditor.md`** | 7.8k | ~80 lines | Three phases (Planning → Implementation → Reporting). Explicit collaboration с security-engineer, penetration-tester, compliance-auditor, architect-reviewer — direct delegation map |
| **mrwadams/stride-gpt** | 1k | tool | STRIDE threat modeling automated, supports Claude 4.5 + extended thinking. Auto-detects MCP topologies, RAG, tool ecosystems → maps to STRIDE. Extended OWASP LLM Top 10 + OWASP ASI |
| **stfbk/PILLAR** | research | LINDDUN tool | Privacy threat modeling (LINDDUN framework). 3 modes (SIMPLE / GO / PRO). Critical для GDPR if health data |
| **semgrep/mcp** + **GitGuardian/ggmcp** + **Snyk MCP** | various | production MCPs | Three-layer detection: SAST (Semgrep) + secrets (GitGuardian) + SCA (Snyk) |
| **ASTRIDE framework** (arxiv:2512.04785) | academic | research | Agentic AI threat modeling — academic base для MCP threat model |

5 production sources + 1 academic foundation.

## 2. Stack tools mapping

Already in voltagent-qa-sec namespace (verified):
- `security-auditor` — orchestration, evidence, finding classification
- `penetration-tester` — exploitation proof для Critical/High findings
- `compliance-auditor` — GDPR/SOC2/PCI/ISO mapping
- `architect-reviewer` — design review (auth, exposure, transport)

Plus:
- `pr-review-toolkit:silent-failure-hunter` — error handling audit
- `voltagent-infra:security-engineer` — remediation automation

External MCPs:
- `semgrep/mcp` — official SAST
- `GitGuardian/ggmcp` — secrets (500+ types)
- `Snyk MCP` — SCA + SAST
- `Trivy` (CLI) — container + IaC

## 3. Top-3 Gimle-specific gaps (authored prompts needed)

### 3.1 MCP threat model для palace-mcp
Generic prompts cover web APIs but не: MCP tool poisoning, SSE stream injection (CVE-2025-56406 class), prompt injection через Neo4j graph, no-auth default in MCP spec. **Use ASTRIDE** as academic base + custom checklist.

### 3.2 sops + Docker Compose supply chain
Authored skill: parse `docker-compose.yml` + `sops.yaml` → check CIS Docker Benchmark v1.6 + sops KMS rotation policy. Use `docker-bench-security` via Bash.

### 3.3 Cloudflared tunnel scope audit
Not covered: Access policies scope creep, service token rotation, audit log review, JWT audience binding. Need Cloudflare One API calls для policy extraction + least-privilege validation.

## 4. Workflow decomposition (key value)

SecurityAuditor — **smart coordinator**. Decomposes request into 4 phases:

```
Phase 1 PARALLEL: architect-reviewer + security-engineer (infra) + Semgrep MCP
Phase 2 SEQUENTIAL (depends Phase 1): threat-modeling + penetration-tester
Phase 3 COMPLIANCE (parallel Phase 2): compliance-auditor (if scope требует)
Phase 4 SYNTHESIS (own): prioritize + risk-score + remediation plan
```

Никогда не читает код сам. Делегирует, агрегирует с CVSS + business context, escalates Critical/High через penetration-tester для exploitation proof.

## 5. Final template structure (~95 lines role)

1. Role: smart orchestrator, NOT executor
2. Audit types table (6 types × triggers × outputs)
3. 5 principles (no code reading, static-first, risk scoring, escalation discipline, smallest safe change)
4. Workflow decomposition (4 phases с subagent calls)
5. Subagent invocation matrix (when to invoke vs when NOT)
6. MCP servers (Semgrep / GitGuardian / Snyk / Trivy)
7. 3 Gimle-specific authored gaps (MCP threats / sops audit / cloudflared scope)
8. Audit deliverable checklist
9. Skills + fragment includes
