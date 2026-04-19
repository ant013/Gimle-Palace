# Palace — git-mcp read-only exposure

**Date:** 2026-04-19
**Slice:** N+1.5 (bridge between N+1 multi-project and N+2 extractors)
**Author:** Board (operator-driven brainstorm)
**Status:** Awaiting formalization (Phase 1.1)
**Predecessors pinned:**
- `develop@7bdc302` — GIM-53 multi-project scoping merged (`:Project` node, `group_id` namespace on all nodes, `register_project` / `list_projects` / `get_project_overview` tools).
- `main@aabb1d7` — latest meta-commit (N+1b rev3 rename + revert runbook).
- `docs/research/extractor-library/report.md §8` — N+2 roadmap (item #22 Git History Harvester is the complementary *systematic* ingest slice; this spec is the *ad-hoc read* complement).
**Related memories (operator):**
- `project_backlog.md` — backlog entry originally tagged «thin git-mcp read-only exposure». This spec formalizes the surface as 5 read-only tools (log/show/blame/diff/ls_tree) — narrow vs full git (~20 commands) but not minimalist. Backlog memory updates post-merge to match actual scope.
- `reference_graphiti_core_api_truth.md` — unrelated to this slice (no graphiti / embedding dependency).
- `feedback_qa_skipped_gim48.md` — three-gate discipline applies; mock-only tests forbidden for substrate-touching code.

## 1. Context

After GIM-52/53, palace-mcp exposes a curated `palace.memory.*` surface (lookup/health/register_project/list_projects/get_project_overview) over Neo4j. Clients (Claude Code via SSH tunnel, paperclip agents on the Docker-internal network) have *no* way to run `git log / blame / diff` against registered repos directly — they would have to SSH into the iMac and shell out manually. Git history sits inside the knowledge graph only after the N+2 Git History Harvester extractor ships. Before that slice, ad-hoc git questions ("who last touched `config.py`?", "what changed between two SHAs?") have no tool surface.

**Gap is categorical.** It's the only one left between Gimle-Palace and external markdown+MCP stacks that bundle git tools. Cost: ~1 day of work, narrow scope, zero schema changes to the graph.

**Two write paths to palace will coexist** and are deliberately separate:
- **This slice (read passthrough).** Agent calls `palace.git.log(...)` → subprocess → text/JSON response. Nothing touches Neo4j.
- **N+2 Git History Harvester (future).** Scheduled extractor walks full repo history → writes `:Commit`, `:File`, `:TOUCHED` nodes/edges idempotently by `commit_sha`. Agents then query structured history via `palace.memory.lookup(entity_type="Commit", ...)`.

The two paths are not parallel work for the agent: one answers ad-hoc text questions cheaply; the other answers structured historical queries via graph. They do not duplicate each other's effort.

## 2. Goal

After this slice:

- Claude Code (external, via tunnel) and paperclip agents (Docker-internal) can call `palace.git.log / show / blame / diff / ls_tree` against any project registered in `:Project` and mounted into palace-mcp container.
- Tool surface is strictly **read-only**: filesystem bind-mount is `read_only: true`, subprocess command whitelist refuses any write verb, no graph writes as side-effect.
- Output is consistent, capped server-side, Pydantic-typed; `truncated: true` signals when caps hit. Clients don't pay for unbounded output accidentally.
- `palace.memory.health` gains a `git` section listing available vs unregistered projects.
- QA live-smoke (Phase 4.1) includes a real `git log` call returning real develop commits + a security test (path traversal attempt).

**Success criterion.** After merge:
1. `palace.git.log(project="gimle", n=5)` from Claude Code returns the 5 most recent develop commits (`7bdc302`, `e629d97`, `126eb49`, `a4abd28`, `8a660b8` at time of writing).
2. `palace.git.log(project="gimle", path="../../etc/passwd")` returns `{ok: false, error_code: "invalid_path"}` without touching subprocess.
3. `palace.git.blame(project="gimle", path="services/palace-mcp/src/palace_mcp/main.py", line_start=1, line_end=5)` returns 5 structured blame entries with SHA + author + ISO date.
4. `palace.memory.health()` response includes `"git": {"repos_root": "/repos", "available_projects": ["gimle"], "unregistered_projects": []}`.

## 3. Architecture

### 3.1 Placement

Tools register on the **existing** `FastMCP("palace-memory")` in `services/palace-mcp/src/palace_mcp/mcp_server.py`. No second FastMCP app, no new port, no new container. Client sees one MCP endpoint, one auth model (internal Docker network, no per-call auth).

### 3.2 New package layout

```
services/palace-mcp/src/palace_mcp/git/
├── __init__.py
├── path_resolver.py   # slug → Path("/repos/slug"); validate existence + is_git_dir
├── command.py         # run_git(args, repo_path) -> GitResult; subprocess-only module
├── schemas.py         # Pydantic response models for 5 tools + error envelope
└── tools.py           # 5 MCP tool handlers; parse stdout, apply caps, shape response
```

Each unit has **one clear responsibility** and is testable in isolation:
- `path_resolver` — pure function, `tmp_path`-fixture tests.
- `command` — single subprocess surface, whitelist-enforced, env-sanitized; mockable centrally for error paths but called live for happy path.
- `schemas` — Pydantic `BaseModel`s with `ConfigDict(extra="forbid")` (matching `memory/schema.py` convention).
- `tools` — declarative MCP handlers, no subprocess knowledge directly.

### 3.3 Data flow (`palace.git.log` example)

1. FastMCP decodes JSON, Pydantic validates types.
2. `path_resolver.resolve("gimle")` → `Path("/repos/gimle")` or raises `ProjectNotRegistered`.
3. `command.run_git(["log", "--pretty=format:%H%x00%h%x00%an%x00%ae%x00%aI%x00%s", "-n", str(n), ref, "--"] + ([path] if path else []), repo_path=...)` → `GitResult(stdout, stderr, rc, duration_ms)`.
4. `tools.parse_log(stdout)` parses NULL-delimited records into a list of `LogEntry` dicts.
5. If parser hit cap → `truncated: true` in response envelope.
6. Response: `LogResponse(ok=True, project="gimle", ref=ref, entries=[...], truncated=False)`.

### 3.4 Compose delta

```yaml
palace-mcp:
  # ... existing unchanged
  volumes:
    - type: bind
      source: /Users/Shared/Ios/Gimle-Palace
      target: /repos/gimle
      read_only: true
    # Future projects (example, commented until ready):
    # - type: bind
    #   source: /Users/Shared/Ios/Medic
    #   target: /repos/medic
    #   read_only: true
```

**Convention:** inside the container, a project with slug `X` is at `/repos/X`. Host-side path is explicit per-project in compose — no symlink magic, no root bind-mount, no directory renames.

**No new env var.** Container sees `/repos` as a compile-time constant (`REPOS_ROOT = Path("/repos")` in `path_resolver.py`).

### 3.5 Dockerfile delta (one line)

`services/palace-mcp/Dockerfile:27` (line number at time of writing; impl task will pattern-match on the `apt-get install` line, not rely on the line number) changes from:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
```

to:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*
```

Size impact: ~30 MB (git + libs). Runtime user remains `appuser` (non-root). `python:3.12-slim` is currently built on `debian:bookworm` shipping `git 2.39.5`; the `safe.directory=*` mechanism (§5.5) requires git ≥ 2.31 — comfortably satisfied.

### 3.6 Authority separation between graph and git layers

**Filesystem bind-mount is the authority for `palace.git.*`.** A project is addressable by git tools iff `/repos/<slug>/.git/` exists inside the container. No Neo4j lookup on the hot path — per §3.3, `path_resolver.resolve()` is a pure FS call.

**`:Project` in Neo4j is the authority for `palace.memory.*`.** `list_projects`, `get_project_overview`, `lookup` read from the graph; FS state is irrelevant to them.

The two surfaces are **independent by design**: a repo mounted without `register_project` is usable for git reads but absent from graph queries; a registered project with no mount appears in `list_projects` but `palace.git.log` returns `project_not_registered`. Rationale:
- Cypher on every git call doubles latency without closing any security hole (mount is already operator-gated).
- Registration is graph metadata (name / tags / language / framework / repo_url) — none of which git needs.
- Operational skew surfaces via `health().git.unregistered_projects` (§6.2); it is an operator alert, not a security gate.

This choice is deliberate. Conflating mount-auth and registration-auth would mean either every git call does Cypher (slow) or every bind-mount triggers automatic graph registration (magic). Both worse than two explicit surfaces.

## 4. Tool surface

Five tools. Consistent envelope: `{ok, project, truncated, ...data}` on success; `{ok: false, error_code, message, project?}` on error. All responses are Pydantic models.

### 4.1 `palace.git.log`

**Input:** `project: str, path: str | None, ref: str = "HEAD", n: int = 20, since: str | None, author: str | None`
Hard cap: `n` effective ≤ 200.
**Command:** `git log <ref> --pretty=format:'%H%x00%h%x00%an%x00%ae%x00%aI%x00%s' -n <n> [--author=<X>] [--since=<X>] [-- <path>]`
**Response:** `LogResponse(ok, project, ref, entries: list[LogEntry(sha, short, author_name, author_email, date, subject)], truncated)`.

### 4.2 `palace.git.show`

**Input:** `project: str, ref: str, path: str | None`
Two modes:
- `path=None` → commit detail (meta + stat + diff). Cap 500 lines across `diff`.
- `path=<file>` → file content at `ref`. Cap 500 lines.

**Commands:**
- Commit mode: `git show <ref> --stat -p`
- File mode: `git show <ref>:<path>`

**Response variants:**
- `ShowCommitResponse(ok, mode="commit", project, sha, author_name, date, subject, body, files_changed: list[FileStat(path, added, deleted, status)], diff, truncated)`
- `ShowFileResponse(ok, mode="file", project, ref, path, content, lines, truncated)`

**Binary file detection (file mode only).** Before UTF-8-decoding stdout, scan the first 8192 bytes for a NUL byte. If found → return `{ok: false, error_code: "binary_file", project, ref, path, size_bytes}` (size from a cheap `git cat-file -s <ref>:<path>` lookup). Clients wanting binary blobs are out of scope; we do not stream binary content over MCP, and `errors="replace"` would just produce 500 lines of U+FFFD — worse than a clean error.

### 4.3 `palace.git.blame`

**Input:** `project: str, path: str, ref: str = "HEAD", line_start: int | None, line_end: int | None`
Without `line_*`: hard cap 400 lines.
**Command:** `git blame --porcelain <ref> [-L <start>,<end>] -- <path>`
**Response:** `BlameResponse(ok, project, path, ref, lines: list[BlameLine(line_no, sha, short, author_name, date, content)], truncated)`.

Porcelain format is used for reliable parsing (commit metadata de-duplicated per SHA in porcelain; parser reconstructs per-line view).

### 4.4 `palace.git.diff`

**Input:** `project: str, ref_a: str, ref_b: str, path: str | None, mode: Literal["full", "stat"] = "full", max_lines: int = 500`
Caps:
- `mode="full"`: `max_lines` effective ≤ 2000.
- `mode="stat"`: bounded by file-row count, hard cap 500.

**Commands:**
- `mode="full"`: `git diff <ref_a> <ref_b> [-- <path>]`
- `mode="stat"`: `git diff --numstat <ref_a> <ref_b> [-- <path>]`

**Response:** `DiffResponse(ok, project, ref_a, ref_b, path, mode, diff: str | None, files_stat: list[FileStat(path, added, deleted)] | None, truncated)`.

Exactly one of `diff` / `files_stat` is populated per response. `mode="stat"` is the token-efficient path for cross-version comparisons on monorepos: a 10k-line change compresses to ~50 rows. `mode="full"` returns unified-diff text. Binary files appear in `files_stat` with `added=None, deleted=None` (git's `-\t-\t<path>` rendition, parsed to nulls).

### 4.5 `palace.git.ls_tree`

**Input:** `project: str, ref: str = "HEAD", path: str | None, recursive: bool = False`
Cap: 500 entries.
**Command:** `git ls-tree [-r] <ref> [<path>]`
**Response:** `LsTreeResponse(ok, project, ref, path, recursive, entries: list[TreeEntry(path, type, mode, sha)], truncated)`.

### 4.6 Response invariants (all tools)

- `sha` — full 40-char hex.
- `short` — `%h` with `--abbrev=7` (fixed 7).
- `date` — ISO-8601 with timezone (`%aI`).
- `path` — POSIX, forward slashes, relative to repo root.
- `truncated=true` means caps hit → more data exists; client increases `n`/`max_lines` to see more.
- When `truncated=true`, output is cut at **record boundary** (whole commit / whole blame line / whole tree entry / whole diff hunk line), never mid-record.

## 5. Security

Ten distinct threat → mitigation pairs. All mitigations apply *before* `subprocess` forks where possible.

### 5.1 Slug validation

Regex `^[a-z0-9][a-z0-9\-]{0,62}$`. This slice **creates** a `validate_slug(slug: str) -> None` helper in `memory/projects.py` (raises `InvalidSlug`). At time of writing, `register_project` accepts any string as slug (format validation not implemented yet; relies on Neo4j UNIQUE constraint only — confirmed by reading `memory/project_tools.py:40` + `memory/cypher.py:11`). This slice retrofits `register_project` to call `validate_slug`, and `git.path_resolver.resolve()` calls the same helper. Single source of truth unified across graph and git layers.

Fail → `invalid_slug`, no FS operation.

### 5.2 Path handling — FS-path only, no pathspec

`path` arguments are **strict filesystem paths relative to repo root**, not git pathspecs. Pathspec magic (`:(glob)...`, `:!exclude`, `:/root-magic`, any leading `:`) is rejected at the input layer. For any user-provided `path`:

1. Reject if starts with `:` (pathspec magic prefix).
2. Reject if starts with `/` (absolute).
3. Reject if contains a NUL byte.
4. `(repo_path / user_path).resolve()` and assert `is_relative_to(repo_path.resolve())`.
5. Reject if the resolved target is a symlink pointing outside `repo_path`.
6. For `log` / `diff` (which accept paths that may have existed only historically): if the resolved path does not exist at `HEAD`, still accept — git will return empty results; the traversal check already enforced containment. For `show` / `blame` / `ls_tree` (operate on specific refs): path must resolve under the repo but need not exist at `HEAD`; git returns a clean error if it doesn't exist at the requested ref.

Fail → `invalid_path`. A client wanting pathspec semantics ("all `*.py` files") makes multiple tool calls; a followup slice could add an explicit pathspec-aware tool if demand surfaces.

### 5.3 Argument injection

- Every `subprocess.run` uses `args: list[str], shell=False`. Semicolons / `&&` / `$(...)` in user strings become literal characters.
- Every tool passes `--` (git option terminator) before any user-provided path or ref-used-as-path.
- User-provided refs are regex-filtered: `^[A-Za-z0-9][A-Za-z0-9._/@\-]{0,199}$`. The leading `[A-Za-z0-9]` blocks `-`-prefixed flag injection (ref cannot start with `--`); the remaining chars allow all legitimate ref forms (SHA, branch, tag, `HEAD~N`, `ref@{time}`). No separate `rev-parse --verify` pre-check: git returns rc=128 with `"unknown revision"` / `"bad object"` in stderr for invalid refs, and `command.run_git` maps `rc=128 ∧ stderr contains "unknown revision"` → `invalid_ref`. Single subprocess per tool call (saves ~20-40 ms cold-fork on Docker for every tool with a ref arg).

Fail → `invalid_ref`.

### 5.4 Command whitelist

`command.run_git()` inspects `args[0]`:

```python
ALLOWED_VERBS = frozenset({"log", "show", "blame", "diff", "ls-tree", "cat-file"})
if args[0] not in ALLOWED_VERBS:
    raise ForbiddenGitCommand(args[0])
```

Any future tool code that tries to call `push / fetch / pull / commit / reset / add / config --set / ...` is rejected pre-fork.

### 5.5 Config hijack resistance

Per-call env passed to `subprocess.run`:

```python
SAFE_ENV = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "safe.directory",
    "GIT_CONFIG_VALUE_0": "*",
}
```

- No `$HOME/.gitconfig` / `/etc/gitconfig` reads.
- `safe.directory=*` avoids spurious "unsafe repository" errors from UID mismatch between host-owned files and container `appuser`.
- `GIT_TERMINAL_PROMPT=0` refuses any interactive prompt.

### 5.6 Timeout

Every call uses `timeout=10` seconds. Exceeded → `git_timeout`.

### 5.7 Output size

Stdout is streamed line-by-line via `Popen.stdout.readline()` in a loop that breaks at cap, then `proc.kill()`. stdout is **never fully buffered into memory** before cap enforcement. Protects against pathologically large `git log` / `git diff`.

**stderr handling under cap-kill.** When cap fires, stderr may be partially buffered by git. Correct sequence: `proc.stdout.close(); tail_stderr = proc.stderr.read(4096); proc.kill(); proc.wait(timeout=2)`. Drains stderr into a bounded buffer for error reporting, kills, then reaps. Missing this sequence risks a zombie process or a deadlock when stderr fills its pipe buffer (64 KB typical) while we ignore it. Tested at Level 2 integration (§7).

### 5.8 Binary / encoding

`stdout.decode("utf-8", errors="replace")`. Commit messages with non-UTF-8 bytes don't raise; invalid sequences become U+FFFD.

### 5.9 Read-only filesystem

`read_only: true` on the bind-mount. Any write call that bypasses the whitelist would still fail with EROFS. Defence in depth.

### 5.10 Unified error schema

```
{ok: false, error_code: str, message: str, project?: str}
```

Codes: `invalid_slug | project_not_registered | invalid_path | invalid_ref | forbidden_command | git_timeout | git_error | unknown`. No stack traces returned to clients. Clients match on `error_code`, never on `message`.

## 6. Observability

### 6.1 Logging

One structured log per call:

```json
{"event": "git.tool.call", "ts": "2026-04-19T10:00:00Z", "tool": "palace.git.log",
 "project": "gimle", "duration_ms": 42, "rc": 0, "stdout_bytes": 1842, "truncated": false}
```

On error:

```json
{"event": "git.tool.error", "tool": "palace.git.log", "project": "gimle",
 "error_code": "invalid_path", "git_rc": null, "git_stderr_head": ""}
```

**Not logged:** `path`, `ref`, `author`, `since`, file contents, stdout body. Debugging against real data happens via `docker exec` on iMac.

### 6.2 Health integration

`palace.memory.health` response gains:

```json
{
  "git": {
    "repos_root": "/repos",
    "available_projects": ["gimle"],
    "unregistered_projects": []
  }
}
```

Logic:
- `available_projects` = `os.listdir("/repos/")` filtered by `path.is_dir() and (path/".git").exists()`, computed lazily per health call.
- `unregistered_projects` = `available_projects − {p.slug for p in :Project}`.

**Schema invariant:** `HealthResponse` has `extra="forbid"` on the server side. Adding the `git` field is a server-side additive change. Any downstream Pydantic client parsing server responses with `extra="forbid"` would need a corresponding model update — low risk in practice (no known strict-parsing client; MCP clients consume JSON, not Pydantic). Project rule going forward: `HealthResponse` is **additive-only** — fields are never removed or renamed without a major version bump announced in release notes.

Non-blocking by design (see §3.6 for full authority-separation rationale): git tools answer for any slug backed by a mounted git dir, whether registered in `:Project` or not. `unregistered_projects` is an operator alert for the skew, not a security gate.

### 6.3 Metrics / alerts

None in this slice. Prometheus / OTEL land in a dedicated observability slice later.

## 7. Testing strategy

Five levels. Explicit rejection of mock-heavy testing per `feedback_qa_skipped_gim48.md` (GIM-48 disaster: mocked subprocess would pass while real git fails).

### 7.1 Level 1 — pure unit (no subprocess)

- `path_resolver.validate_slug(...)` — accept `gimle`, `g-mle`, `g123`; reject `Gimle`, `../etc`, `gimle/sub`, empty, 64+ chars.
- `path_resolver.resolve(...)` — existing git dir → Path; missing → `project_not_registered`; dangling symlink → `invalid_path`.
- `tools.parse_log(null_delimited_bytes)` — fixture output from a real `git log` run captured as bytes.
- `tools.parse_blame_porcelain(bytes)` — fixture from real `git blame --porcelain`.
- `tools.parse_ls_tree(bytes)` — fixture from real `git ls-tree`.
- Edge cases: empty output; NULL byte inside a commit message subject (parser resilient); UTF-8 replacement on invalid byte sequence.

### 7.2 Level 2 — integration with real git (pytest fixture)

`tmp_repo` fixture creates a real repo with 2+ commits:

```python
@pytest.fixture
def tmp_repo(tmp_path):
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    run(["git", "init", "-q", "-b", "main"], cwd=repo)
    run(["git", "config", "user.email", "t@t"], cwd=repo)
    run(["git", "config", "user.name", "T"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2\n")
    run(["git", "add", "."], cwd=repo)
    run(["git", "commit", "-m", "initial", "-q"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2-changed\nline3\n")
    run(["git", "commit", "-am", "change", "-q"], cwd=repo)
    return repo
```

All 5 tools run against `tmp_repo` with real subprocess. Assertions on structure (sha length, ISO date, entry count, truncated flag).

### 7.3 Level 3 — security (all Section 5 mitigations covered)

One test per mitigation:
- `log(project="../etc")` → `invalid_slug`.
- `blame(path="/etc/passwd")` → `invalid_path`.
- `blame(path="../../etc/passwd")` → `invalid_path`.
- `log(ref="HEAD; rm -rf /")` → `invalid_ref`.
- `log(ref="--upload-pack=/bin/sh")` → `invalid_ref` (regex) and also guarded by `--`.
- Symlink inside repo → target outside → `invalid_path`.
- Direct call `run_git(["push", "origin"])` (unit-test at `run_git` layer, bypassing MCP surface) → `forbidden_command`.

### 7.4 Level 4 — cap enforcement

- `log(n=5000)` on repo with 50 commits → 50 entries, `truncated=False`.
- `log(n=5000)` on repo with 250 commits → 200 entries, `truncated=True`, last entry complete.
- `diff` across 3000-line change → diff ≤ 2000 lines, last line ends with `\n`, `truncated=True`.
- `blame` without `line_*` on 800-line file → 400 lines, `truncated=True`.
- `ls_tree -r` on tree with 700 entries → 500 entries, `truncated=True`.

### 7.5 Level 5 — live smoke (QA Phase 4.1, iMac)

Per GIM-48 postmortem requirements:
1. `docker compose --profile review up -d --build`.
2. From external Claude Code via tunnel: `palace.git.log(project="gimle", n=5)` → assert SHAs match `git log --oneline -5` run directly on iMac.
3. `palace.memory.health()` → assert `git.available_projects == ["gimle"]`, `git.unregistered_projects == []`.
4. Security live: `palace.git.log(project="gimle", path="../../etc/passwd")` → `error_code="invalid_path"`.
5. Read-only proof: `docker exec palace-mcp touch /repos/gimle/x` → `Read-only file system` (EROFS).
6. Direct Cypher invariant: no new relationships/nodes created during smoke — `MATCH (n) RETURN count(n)` before and after identical.

### 7.6 Coverage checklist (explicit, not a count quota)

Required tests — plan enumerates each as its own TDD pair (red → green → commit). Count is a consequence, not a target.

**Security (one per mitigation in Section 5):**
- §5.1 slug regex accept + reject (≥ 8 cases)
- §5.2 path handling: `:`-pathspec prefix, `/`-absolute, `\0`-NUL, `../`-escape, symlink-escape, path under repo but absent at ref
- §5.3 ref regex: `-`-leading flag injection, `--upload-pack=...`, shell metacharacters pass through literally
- §5.4 command whitelist: unit-level `run_git(["push", ...])` → `forbidden_command` (bypasses MCP surface)
- §5.5 env sanitization: hostile `$HOME/.gitconfig` with `includeIf` — ignored
- §5.6 timeout: synthetic 15-second git call → `git_timeout` at 10s boundary
- §5.7 cap-streaming: stderr drained without deadlock when cap-kill fires
- §5.8 invalid-UTF-8 in commit message → U+FFFD, no raise
- §5.9 `docker exec palace-mcp touch /repos/gimle/x` → EROFS (Linux host); documented caveat on macOS

**Cap enforcement (one per tool):**
- `log(n=5000)` on 250-commit repo → 200 entries, `truncated=True`, last entry whole
- `diff(mode="full", max_lines=5000)` on 3000-line change → 2000 lines, `truncated=True`, last line `\n`-terminated
- `diff(mode="stat")` on 700-file change → 500 file rows, `truncated=True`
- `blame` without `line_*` on 800-line file → 400 lines, `truncated=True`
- `ls_tree(recursive=True)` on 700-file tree → 500 entries, `truncated=True`
- `show` commit mode with 5000-line diff → 500 lines, `truncated=True`

**Happy path (one integration per tool against `tmp_repo`):**
- `log`: 5 entries, fields populated, ISO dates present
- `show`: commit mode + file mode + binary-file detection (tmp_repo commits a PNG fixture)
- `blame`: with + without line range
- `diff`: `mode="full"` and `mode="stat"`
- `ls_tree`: flat + recursive

**Parsers (pure units):**
- `parse_log` NULL-delimited normal; empty output; NUL byte inside commit subject
- `parse_blame_porcelain` multi-commit file; single line; full file
- `parse_ls_tree` blob, tree, submodule type markers
- `parse_numstat` including binary-file rows (`-\t-\t<path>`)

**Error paths (mocks where real reproduction is hard):**
- `subprocess.TimeoutExpired` → `git_timeout`
- `BrokenPipeError` mid-stdout-read → graceful `git_error`
- Missing git binary (simulated by PATH override) → `git_error` with clear message

mypy --strict clean on the new package.

### 7.7 What is mocked / what is not

- **Not mocked:** `subprocess.run` for happy-path integration (Levels 2-4). Tests depend on the real `git` binary. GitHub Actions runners have git preinstalled; local dev assumes system git (documented in CLAUDE.md).
- **Mocked:** only error paths hard to reproduce — `TimeoutExpired`, mid-stream `BrokenPipe`. Mock entry point is `command.run_git` (single surface), not `subprocess.run` directly.

## 8. Provisioning (iMac operator steps, one-time)

1. Verify `/Users/Shared/Ios/Gimle-Palace/.git/` exists.
2. `chmod +rx /Users/Shared/Ios /Users/Shared/Ios/Gimle-Palace` — ensure "others" can traverse + read.
3. Pull new compose file + Dockerfile changes on iMac checkout.
4. `docker compose --profile review up -d --build palace-mcp` — rebuilds with git installed + adds bind-mount.
5. Verify: `docker exec palace-mcp git -C /repos/gimle log -1 --oneline`.
6. From Claude Code: `palace.memory.health()` should show `git.available_projects: ["gimle"]`.

### 8.1 Adding a future project (e.g., Medic)

1. Host: `git clone <medic-url> /Users/Shared/Ios/Medic` (or wherever).
2. `palace.memory.register_project(slug="medic", name="Medic", tags=["crypto"])`.
3. Compose: add volume block `source: /Users/Shared/Ios/Medic, target: /repos/medic, read_only: true`.
4. `docker compose up -d --build palace-mcp`.
5. `palace.memory.health()` confirms `"medic"` in `available_projects` and not in `unregistered_projects`.

## 9. Decomposition (plan-first ready)

Expected plan file: `docs/superpowers/plans/2026-04-19-GIM-NN-git-mcp-read-only.md`. CTO will swap `GIM-NN` when paperclip issue is minted.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Formalize: verify spec+plan paths, mint issue, swap `GIM-NN`, reassign CR. |
| 1 | 1.2 | CodeReviewer | Plan-first; validate every task has test+impl+commit; APPROVE → reassign MCPE. |
| 2 | 2.1 | MCPEngineer | Create `palace_mcp/git/` package skeleton: `path_resolver`, `command`, `schemas`, `tools` + tests scaffold. |
| 2 | 2.2 | MCPEngineer | Create `validate_slug` helper in `memory/projects.py` with `InvalidSlug` exception. Retrofit `register_project` to call it (introduces slug format validation where none exists today). TDD: ≥ 8 accept/reject cases. |
| 2 | 2.3 | MCPEngineer | Implement `path_resolver` using `validate_slug` + path handling guard (pathspec prefix `:`, absolute `/`, NUL, traversal, symlink-escape). TDD: all §5.2 cases. |
| 2 | 2.4 | MCPEngineer | Implement `command.run_git` with whitelist, env sanitization (`safe.directory=*`), timeout, streamed-cap, stderr-drain-on-kill. TDD: whitelist + env + mocked error paths + stderr-race integration test. |
| 2 | 2.5 | MCPEngineer | Implement `schemas.py` Pydantic models for all 5 tools + error envelope. mypy --strict clean. |
| 2 | 2.6 | MCPEngineer | Implement `tools.palace_git_log` + NULL-delimited parser + integration test against `tmp_repo` fixture. |
| 2 | 2.7 | MCPEngineer | Implement `tools.palace_git_show` (commit + file modes) + binary-file detection via 8192-byte NUL scan + `git cat-file -s` size lookup + integration tests incl. PNG fixture. |
| 2 | 2.8 | MCPEngineer | Implement `tools.palace_git_blame` (porcelain parser) + integration tests. |
| 2 | 2.9 | MCPEngineer | Implement `tools.palace_git_diff` with `mode="full" \| "stat"` + numstat parser (binary-file rows) + cap tests. |
| 2 | 2.10 | MCPEngineer | Implement `tools.palace_git_ls_tree` + cap tests. |
| 2 | 2.11 | MCPEngineer | Wire 5 tools into `mcp_server.py` FastMCP registration. End-to-end smoke against live tmp repo via MCP client. |
| 2 | 2.12 | MCPEngineer | Extend `memory.health` with `git` section + additive-only schema note. Test: registered-only, mounted-only, both. |
| 2 | 2.13 | MCPEngineer | Dockerfile: pattern-match `apt-get install ... curl` line and add `git`. Compose: add bind-mount for `gimle`. |
| 2 | 2.14 | MCPEngineer | CLAUDE.md: new "Mounting project repos" section documenting the convention + provisioning steps + macOS read-only caveat. |
| 3 | 3.1 | CodeReviewer | Mechanical review: `uv run ruff check && uv run mypy --strict src/ && uv run pytest` output pasted; whitelist / env / cap invariants called out; no admin override. |
| 3 | 3.2 | OpusArchitectReviewer | Adversarial: path-traversal corner cases (mixed-encoding paths, UNC-like, CRLF in ref), subprocess OOM behavior, cap-streaming race conditions. Findings addressed. |
| 4 | 4.1 | QAEngineer | Live smoke on iMac (see §7.5). Evidence comment with commit SHA. |
| 4 | 4.2 | MCPEngineer | Squash-merge. Update checkboxes. Operator does manual iMac redeploy post-merge per current gap. |

Estimated scope: ~600 LOC code (path_resolver ~80, command ~120, schemas ~100, tools ~200, health ext ~40, wiring ~30, tests ~250+). mypy --strict across new package. ~40 new tests. ~3 days wall-clock at agent tempo matching GIM-52/53.

## 10. Acceptance criteria

- [ ] PR against `develop`; squash-merged on APPROVE.
- [ ] 5 new tools on palace-memory MCP: `palace.git.log / show / blame / diff / ls_tree`.
- [ ] `validate_slug` helper exists in `memory/projects.py`; `register_project` calls it; attempting to register `"../etc"` → `InvalidSlug`.
- [ ] All tools return `truncated: true` when caps hit; cap hits at record boundary.
- [ ] Pathspec prefix rejected: `log(path=":(glob)*.py")` → `invalid_path`; other §5.2 cases → `invalid_path`.
- [ ] Ref regex blocks flag injection: `log(ref="--upload-pack=x")` → `invalid_ref`; unknown ref (regex-valid but non-existent) → `invalid_ref` via stderr parse, single subprocess.
- [ ] `run_git(["push", ...])` at unit layer → `forbidden_command`.
- [ ] `diff(mode="stat")` returns `files_stat` only; `mode="full"` returns `diff` text only; binary files appear in `files_stat` with `added=None, deleted=None`.
- [ ] `show(ref=..., path=<binary>)` → `binary_file` error with `size_bytes`.
- [ ] Bind-mount `read_only: true`; `docker exec palace-mcp touch /repos/gimle/x` → EROFS on Linux; macOS caveat documented if applicable.
- [ ] Dockerfile installs `git`; rebuild size delta ≤ 50 MB.
- [ ] `palace.memory.health().git.available_projects == ["gimle"]` on current iMac state.
- [ ] Coverage checklist from §7.6 all items present (not a count gate).
- [ ] mypy --strict clean; ruff clean; pytest green.
- [ ] Live smoke (Phase 4.1): real `palace.git.log(project="gimle", n=5)` returns real develop SHAs; evidence comment authored by QAEngineer.
- [ ] No Neo4j writes during any git tool call (verified via node-count invariant).
- [ ] CLAUDE.md "Mounting project repos" section added.

## 11. Out of scope

- **Any write to Neo4j / graphiti as side-effect of a git call.** Systematic history ingest = N+2 Git History Harvester (`docs/research/extractor-library/report.md §8` item #22). This slice is ad-hoc read only.
- **Per-caller authorization.** palace-mcp `:8080` has no per-call auth today. When N+1c rev3 introduces `:8002` agent MCP with `allowed_group_ids`, git tools may be offered there too with group_id scoping — that is a followup, not this slice.
- **Extended git surface**: `status`, `branch_list`, `tag_list`, `rev_parse` (as a tool), `describe`, `shortlog`, `cat-file`. Adding them later is a small amendment; YAGNI for the gap-closing slice.
- **Write commands**: `commit`, `push`, `fetch`, `pull`, `reset`, `config --set` — never in scope.
- **Clone-on-demand / arbitrary URL**: clients cannot ask git-mcp to clone a new repo. Adding a project requires operator action (compose volume + `register_project`).
- **Observability beyond logs**: Prometheus / OTEL / tracing — separate slice.
- **Auto-deploy on merge**: iMac redeploy stays manual per `reference_post_merge_deploy_gap.md`; N+1c rev3 is the slice that adds the HMAC deploy listener.
- **Concurrent-call rate limiting.** Per-call `timeout=10` bounds individual cost, but 50 parallel `palace.git.log` calls fork 50 git processes. Single-user iMac deployment means practical concurrency is ~1. Adversarial abuse surface belongs to a future `:8002` agent MCP slice (N+1c rev3) with per-token rate limits; not this slice.
- **macOS bind-mount `read_only: true` caveat.** On Linux hosts, `read_only: true` on a bind-mount is kernel-enforced. On macOS Docker Desktop (VM-based), the file-sharing layer (gRPC-FUSE / VirtioFS) may admit writes despite the flag for some operations. Defence-in-depth via command whitelist (§5.4) stays load-bearing regardless — the bind-mount flag is belt, whitelist is suspenders. Operator verification at QA Phase 4.1: `docker exec palace-mcp touch /repos/gimle/x` should fail with EROFS; if it succeeds on macOS, record the caveat in followups and proceed (whitelist still holds).

## 12. Followups

- When N+2 Git History Harvester lands: `palace.memory.lookup(entity_type="Commit", filters=...)` becomes the structured query path; `palace.git.*` remains for ad-hoc text reads.
- When N+1c rev3 adds `:8002` agent MCP + `allowed_group_ids`: optionally mirror git tools on `:8002` with per-token project scoping.
- Additional git verbs (`rev_parse` / `describe` / `shortlog`) — add per demand, one at a time.
- If `stats` on diff becomes valuable (hotspot queries), add `palace.git.diff_stats(project, ref_a, ref_b)` as a sibling tool (separate subprocess call, cheap).
- Close `reference_post_merge_deploy_gap.md` after N+1c rev3 ships, not this slice.

## 13. Estimated size

- Code: ~600 LOC (path_resolver ~80, command ~120, schemas ~100, tools ~200, health extension ~40, mcp_server wiring ~30, tests ~250+).
- Plan + docs: ~90 LOC (CLAUDE.md section ~20, plan file ~70).
- 1 PR, 4-5 handoffs (MCPE → CR → Opus → MCPE → QA → MCPE merge).
- Duration: ~3 days agent-time.
