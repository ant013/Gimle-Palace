# GIM-925 — Stable Operator Runbook

**Date:** 2026-05-27
**Issue:** GIM-925 (PR9 of G0.6)
**Branch:** `pr9/GIM-914-operator-runbook`

## Goal

Consolidate scattered runbooks into a single product-ready operator path at
`docs/runbooks/operator-guide.md`. A new operator must be able to go from
zero to running smoke + semantic analysis without reading chat history.

## Steps

### 1. Audit existing runbooks and extract operator-relevant content

- [x] Read all runbooks under `docs/runbooks/`
- [x] Identify operator-facing vs. developer/agent-internal content
- **Owner:** CTO
- **Affected:** `docs/runbooks/` (read-only audit)

### 2. Write consolidated operator guide

Structure:
1. Prerequisites (hardware, software, accounts)
2. Install & First Start (clone, .env, docker compose, health)
3. Model Cache Setup (Qodo/HF, local-only mode)
4. Repo Mounts (iMac convention, override for non-iMac)
5. Running Runtime Smoke (recipe + binding, CLI invocation)
6. Running Semantic Analysis (project analyze)
7. Do-Not-Delete List (Qodo/HF cache, repo clones, Neo4j data, evidence reports)
8. Cleanup Policy (safe/reclaim/destructive, dry-run default)
9. Common Failures & Troubleshooting

- **Owner:** CTO
- **Affected:** `docs/runbooks/operator-guide.md` (new)

### 3. Add cross-references from existing runbooks

Link from `ingest-swift-kit.md`, `xcode-app-ingest.md`, `xcode-app-scip-emit.md`,
`productized-runtime-smoke.md` back to the consolidated guide where appropriate.

- **Owner:** CTO
- **Affected:** existing runbook files (add "see also" links)

## Acceptance Criteria

- New operator can run documented happy path without chat history.
- Every command has expected output or success criteria.
- Troubleshooting covers: Docker rebuild hangs on ML deps, Neo4j auth/volume
  mismatch, missing Xcode vs server-only, missing SCIP path, local-only model
  cache failure, semantic matrix underfill.
- "Do not delete" list present with rationale.
- Cleanup commands: safe (dry-run default), reclaim, destructive (requires flag).
- No secrets/tokens/raw config in copy-paste examples.
