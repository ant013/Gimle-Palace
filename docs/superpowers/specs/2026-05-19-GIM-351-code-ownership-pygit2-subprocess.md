# GIM-351 Spec - code_ownership native git blame

## Goal

Replace the `code_ownership` extractor's per-file `pygit2.Repository.blame(...)`
hot path with native `git blame --line-porcelain`, preserving the existing
ownership model and output schema.

The change is scoped to performance. It must make BitcoinCore-class repositories
finish within the extractor budget without changing scoring, graph schema, or
the GIM-356 build/vendor target filter.

## Background

GIM-356 shipped the build/vendor target filter as defense in depth, but the
BitcoinCore timeout remains because `.build/checkouts/` is not git-tracked in
the reference repo. The remaining target set is first-party Swift files.

Board triage evidence on 2026-05-19:

- `git ls-files | wc -l`: 265 first-party tracked files.
- Stop-list simulation over tracked files: keep 265, skip 0.
- `pygit2.Repository.blame(BitcoinCore.swift)`: 1.736s.
- `git blame --line-porcelain BitcoinCore.swift`: 0.030s.
- Top 20 largest tracked files: pygit2 about 17s; native git about 0.436s.
- Live smoke `palace.ingest.run_extractor code_ownership bitcoin-core`:
  timeout after 300.0s.

Extrapolation: 259 first-party Swift files at about 1.7s per pygit2 blame call
exceeds 300s. Native git should complete the blame phase in seconds.

## Current Behavior

`services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py`
does this for every dirty path:

- Checks the HEAD blob for binary content through pygit2.
- Calls `repo.blame(path, newest_commit=head_oid)`.
- Loads each hunk's commit through pygit2.
- Canonicalizes author identity through `MailmapResolver`.
- Aggregates `BlameAttribution` by canonical author id.

`CodeOwnershipExtractor._run` already filters dirty paths through
`should_skip_path` before max-file cap, blame, churn, scoring, and write batching.
Deleted-path cleanup remains intentionally unfiltered.

## Decision

Use a hand-rolled porcelain parser around native `git`, not a new PyPI
dependency.

Reasons:

- The exact `git-blame-parser` Python package was not found on PyPI at
  `https://pypi.org/project/git-blame-parser/` on 2026-05-19.
- The exact `git_blame_parser` name appears as a Rust crate on docs.rs, not a
  Python dependency.
- The repo already has a small porcelain parser pattern in
  `palace_mcp.git.tools.parse_blame_porcelain`.
- Git's own docs define the porcelain header and metadata fields needed here:
  `author`, `author-mail`, `author-time`, and `author-tz`.
- Adding a dependency for this narrow parser would increase supply-chain and
  lockfile churn without reducing implementation risk.

Implementation should live in the code ownership extractor boundary, because the
needed output shape differs from the `palace.git.blame` MCP response. Reuse the
existing parser style if useful, but do not change `palace.git.*` public tool
schemas for this issue.

## Scope

In scope:

- Add a subprocess-backed blame helper for `code_ownership`.
- Parse `git blame --line-porcelain HEAD -- <path>` into the same per-file,
  per-author `BlameAttribution` aggregation currently returned by `walk_blame`.
- Preserve existing `MailmapResolver` canonicalization behavior, including the
  pygit2 mailmap path when available.
- Preserve binary/skipped path semantics: binary or unblamable files are omitted
  from blame data and returned in `binary_paths`.
- Add explicit `.mailmap` parity coverage.
- Add parity coverage against pygit2 on the existing synthetic ownership fixture.
- Add a BitcoinCore smoke gate.

Out of scope:

- Changing scoring formula: `alpha * blame_share + (1 - alpha) * recency_churn_share`.
- Changing `:OWNED_BY`, `:OwnershipCheckpoint`, file state, or audit schema.
- Changing the GIM-356 stop-list behavior.
- Replacing pygit2 elsewhere, including git_history.
- Adding sampling, shallow blame, cache persistence, or CPU allocation changes.

## Functional Requirements

1. `walk_blame(...)` keeps its current caller-facing API unless the implementer
   proves a smaller local signature change is required.
2. For each input path, native git blame is run from the repository workdir with
   an argv list and `shell=False`.
3. The command uses `--line-porcelain` so author metadata is available per
   blamed line without maintaining commit metadata state across groups.
4. The parser extracts at minimum:
   - commit sha
   - final line number or equivalent line count
   - author name
   - author email
   - author time
5. Author identity is passed through the existing `MailmapResolver.canonicalize`.
6. Bot filtering remains keyed by canonical email.
7. `last_commit_at` remains the max author timestamp for each canonical author.
8. Non-zero git exits for binary, missing, or unsupported paths are handled like
   today's pygit2 blame failures: log at info level, skip the path, and do not
   fail the extractor.
9. Unexpected parser failures should skip only the affected path unless they
   indicate a programmer error caught by tests.

## Non-Functional Requirements

- No new runtime dependency.
- No shell interpolation.
- No logging of file contents or email-heavy blame output.
- Keep code small. Target: one focused helper/parser plus tests, not a git tool
  subsystem refactor.
- Keep `code_ownership` output stable for existing integration tests.

## Acceptance Criteria

- `code_ownership` completes in <60s on the BitcoinCore reference repo.
- Existing smaller-repo integration coverage still passes.
- Pygit2 vs native blame attribution is within +/-2 percent owner-share parity
  on the existing code ownership integration fixture.
- `.mailmap` parity test proves an alias identity is canonicalized to the same
  owner as the current resolver path.
- Binary-file behavior remains covered.
- Vendor/build paths remain filtered before blame, preserving GIM-356.
- PR targets `develop`, references this spec and the plan file, has green CI,
  CXCodeReviewer approval, adversarial review, and CXQAEngineer smoke evidence.

## Verification

Minimum implementation gate:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py
uv run pytest tests/extractors/integration/test_code_ownership_integration.py
uv run ruff check src/palace_mcp/extractors/code_ownership tests/extractors/unit/test_code_ownership_blame_walker.py tests/extractors/integration/test_code_ownership_integration.py
```

QA smoke gate:

```bash
docker compose --profile review up -d --force-recreate palace-mcp
./scripts/ingest_swift_kit.sh bitcoin-core
```

QA evidence must include runtime for `code_ownership`, a first-party ownership
sample, and confirmation that `.build/checkouts/` ownership paths are absent.
