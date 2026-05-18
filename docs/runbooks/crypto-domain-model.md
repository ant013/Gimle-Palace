# Runbook: crypto_domain_model extractor

> GIM-239 · Roadmap #40 · Audit-V1 S2.1

## Overview

The `crypto_domain_model` extractor scans Swift source files with semgrep custom rules
and writes `:CryptoFinding` nodes to Neo4j. Results feed the audit report pipeline via
`palace.audit.run_audit(extractor="crypto_domain_model", project=<slug>)`.

## Prerequisites

- `semgrep >= 1.162.0` is installed in the palace-mcp venv (added to `pyproject.toml`).
- The target repo is bind-mounted in `docker-compose.yml` at `/repos/<slug>` (read-only).
- No SCIP file or extra env vars are needed — the extractor walks the repo directly.

## Running the extractor

```
palace.ingest.run_extractor(name="crypto_domain_model", project="uw-ios")
```

Response shape (success):
```json
{"ok": true, "run_id": "<uuid>", "extractor": "crypto_domain_model",
 "project": "uw-ios", "duration_ms": 4200,
 "nodes_written": 12, "edges_written": 0, "success": true}
```

## Querying results

```cypher
MATCH (f:CryptoFinding {project_id: "project/uw-ios"})
RETURN f.kind, f.severity, f.file, f.start_line, f.message
ORDER BY CASE f.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
          WHEN 'medium' THEN 2 ELSE 3 END, f.file, f.start_line
```

Via MCP audit tool:
```
palace.audit.run_audit(extractor="crypto_domain_model", project="uw-ios", kit_name="UnstoppableWallet-iOS")
```

## Semgrep rules inventory

| File | Rule IDs | Kind | Severity |
|------|----------|------|----------|
| `private_key_string_storage.yaml` | `mnemonic_userdefaults_storage` | `private_key_string_storage` | ERROR |
| `private_key_string_storage.yaml` | `private_key_type_string` | `private_key_string_storage` | HIGH |
| `private_key_string_storage.yaml` | `words_joined_userdefaults` | `private_key_string_storage` | ERROR |
| `decimal_raw_uint_arithmetic.yaml` | `decimal_raw_uint_arithmetic_div` | `decimal_raw_uint_arithmetic` | WARNING |
| `decimal_raw_uint_arithmetic.yaml` | `decimal_raw_uint_arithmetic_mul` | `decimal_raw_uint_arithmetic` | WARNING |
| `bignum_overflow_unguarded.yaml` | `bignum_overflow_unguarded` | `bignum_overflow_unguarded` | WARNING |
| `bignum_overflow_unguarded.yaml` | `bignum_overflow_unguarded_sub` | `bignum_overflow_unguarded` | WARNING |
| `address_no_checksum_validation.yaml` | `address_no_checksum_validation` | `address_no_checksum_validation` | WARNING |
| `wei_eth_unit_mix.yaml` | `wei_eth_unit_mix` | `wei_eth_unit_mix` | WARNING |

Rules live in `services/palace-mcp/src/palace_mcp/extractors/crypto_domain_model/rules/`.

## Deduplication (D5)

Multiple semgrep rules may fire on the same source location. The extractor coalesces
findings by `(file, start_line, end_line, kind)` and keeps the highest severity.
Severity rank (highest → lowest): `critical > high > medium > low > informational`.

## Known limitations (heuristic v1)

1. **Type-blind variable matching** — rules use `metavariable-regex` on variable
   names, not types. A variable named `balance` of type `BigUInt` (safe) still
   triggers `bignum_overflow_unguarded`. Expected FP rate ≈5% on well-typed code.

2. **`metavariable-type` not supported for Swift** in semgrep 1.162.0. Eliminating
   type-based FPs requires a future semgrep upgrade or an AST post-filter.

3. **Swift `guard`/`do-catch` wrappers** not parsed — the extractor does not
   distinguish guarded arithmetic from unguarded.

4. **Bundle ingest not wired** — run per-project via `run_extractor(project=...)`.
   Bundle-level support (aggregate across HS Kits) is a follow-up.

## Tuning

| Env var | Default | Notes |
|---------|---------|-------|
| `PALACE_CRYPTO_SEMGREP_TIMEOUT_S` | `120` | Per-run timeout for semgrep subprocess |

## Troubleshooting

**`extractor_config_error: semgrep timed out`**
Increase `PALACE_CRYPTO_SEMGREP_TIMEOUT_S` in `.env` and restart the container.
Large repos (>10k Swift files) typically finish in <60 s on an M-series Mac.

**`extractor_config_error: semgrep exited N`**
A non-0/1 exit code means semgrep itself errored. Check the container logs:
```bash
docker logs palace-mcp 2>&1 | tail -50
```
Semgrep exits 0 = no findings; 1 = findings found; 2+ = internal error.

**Zero findings on a repo known to have issues**
Verify the repo is mounted and semgrep can read it:
```bash
docker exec palace-mcp semgrep --version
docker exec palace-mcp ls /repos/<slug>/
```
Also check that `.semgrepignore` inside the repo is not excluding all Swift files.

**`extractor_config_error: semgrep rules directory not found`**
The container image may be stale. Rebuild with `bash paperclips/scripts/imac-deploy.sh`.

## Neo4j schema

Nodes written: `:CryptoFinding`

| Property | Type | Description |
|----------|------|-------------|
| `project_id` | string | `"project/<slug>"` |
| `kind` | string | Rule family (e.g. `bignum_overflow_unguarded`) |
| `severity` | string | Normalised: `critical/high/medium/low/informational` |
| `file` | string | Repo-relative path |
| `start_line` | int | First line of match |
| `end_line` | int | Last line of match |
| `message` | string | Semgrep rule message |
| `run_id` | string | UUID of the extractor run |

Constraint: `crypto_finding_unique` on `(project_id, kind, file, start_line, end_line)`.
Indexes: `crypto_finding_project` on `(project_id)`, `crypto_finding_severity` on `(severity)`.
