# Code Ownership Extractor — Runbook

## What it does

Computes file-level ownership from `git_history` graph (GIM-186) +
`pygit2.blame` on HEAD. Writes `(:File)-[:OWNED_BY]->(:Author)` edges
with `weight = α × blame_share + (1-α) × recency_churn_share`. Single
MCP tool: `palace.code.find_owners`.

## Trust assumptions

`find_owners` enumerates committer emails for any registered project.
Project-level ACLs are NOT implemented in palace-mcp. Treat the tool
as PII-bearing in multi-tenant deployments. Single-tenant or trusted-
team setups can run without restriction.

## Running

Prereq: `git_history` extractor (GIM-186) has indexed at least one
commit for the target project.

```
palace.ingest.run_extractor(name="code_ownership", project="<slug>")
palace.code.find_owners(file_path="<path>", project="<slug>", top_n=5)
```

## Knobs

| Env | Default | Effect |
|-----|---------|--------|
| `PALACE_OWNERSHIP_BLAME_WEIGHT` | 0.5 | α in `α × blame + (1-α) × churn` |
| `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` | 50_000 | DIRTY-set hard cap |
| `PALACE_OWNERSHIP_WRITE_BATCH_SIZE` | 2_000 | Phase-4 tx batching |
| `PALACE_MAILMAP_MAX_BYTES` | 1 048 576 | `.mailmap` size cap |
| `PALACE_RECENCY_DECAY_DAYS` | 30 | half-life for recency decay (substrate) |

## `.mailmap` recipes

Place `.mailmap` in repo root. Standard format:
```
Real Name <real@example.com> Old Name <old@example.com>
```
v1 uses pygit2 only (no custom parser). Oversized files (>
`PALACE_MAILMAP_MAX_BYTES`) → identity passthrough; check
`:IngestRun.mailmap_resolver_path = 'identity_passthrough'` after run
and either trim `.mailmap` or raise the cap.

## Erasure (PII / right-to-be-forgotten)

```cypher
MATCH (a:Author {provider: 'git', identity_key: $email_lc})
OPTIONAL MATCH (a)<-[r:OWNED_BY {source: 'extractor.code_ownership'}]-()
DELETE r
WITH a
OPTIONAL MATCH (a)<-[any]-()
WITH a, count(any) AS remaining
WHERE remaining = 0
DELETE a
```

For tombstoning instead of deleting (preserves git_history shape):
```cypher
MATCH (a:Author {provider: 'git', identity_key: $email_lc})
SET a.email = 'redacted-' + apoc.util.sha1(a.identity_key),
    a.name = 'redacted'
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `git_history_not_indexed` | GIM-186 has not run for this project | run `palace.ingest.run_extractor(name='git_history', project='<slug>')` first |
| `ownership_max_files_exceeded` | HEAD tree larger than cap | raise `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` |
| `ownership_diff_failed` | local clone diverged from checkpoint SHA | `git fetch` in the mounted clone, retry |
| `repo_head_invalid` | corrupt refs / detached HEAD | `git fsck` in clone, reset to a valid branch |
| `find_owners` returns `no_owners_reason='file_not_yet_processed'` | file added since last extractor run | re-run extractor |
| `find_owners` returns `no_owners_reason='binary_or_skipped'` | binary / submodule / symlink — by design | n/a |
| Bot-laundered authors appear as humans | `git config user.name` was set to a non-bot string by an actual bot | spot-check `find_owners` for high-stake files; manually fix `:Author.is_bot` if confirmed |

## Bot-laundering spot check

After bootstrap run on a security-critical project:
```
palace.code.find_owners(file_path="<critical-file>", project="<slug>", top_n=10)
```
If a name unfamiliar to the team appears, query their commit history:
```cypher
MATCH (a:Author {provider: 'git', identity_key: '<email>'})
      <-[:AUTHORED_BY]-(c:Commit {project_id: '<slug>'})
RETURN c.sha, c.committed_at
ORDER BY c.committed_at DESC LIMIT 20
```
Inspect commit content for automation patterns (uniform timing, large
mechanical diffs); flip `is_bot` manually if confirmed bot.
