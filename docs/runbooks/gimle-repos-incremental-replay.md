# Runbook: incremental replay for canonical Gimle-Repos copies

Use this runbook to update already registered projects and replay their Palace
extractors on the **canonical** source copies under
`/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`. It is deliberately a
preflight-first procedure: never compensate for a stale, mismapped, or dirty
checkout by indexing another copy.

For the historical `fresh` benchmark mount, use
[`bench/ingest-fresh-replay.sh`](../../bench/ingest-fresh-replay.sh) instead.
That script is not a production source-sync tool.

## Preconditions

- The native `palace-mcp` runtime is healthy on `http://localhost:8765/healthz`.
- You can call `palace.memory.list_projects` and
  `palace.ingest.run_extractor` through an MCP client.
- You know the intended remote ref for every project before changing it. The
  ref is an operator input; never infer it from the default branch or from a
  missing `indexed_commit`. For example, `uw-ios-app` currently uses
  `version/0.50`, while `stable-wallet-ios` uses `version/1.1`.

## Per-project preflight

1. Resolve the project from `palace.memory.list_projects`. Record its slug,
   registered source path, and intended remote ref. The registered path must
   identify the canonical checkout; do not substitute a similarly named clone.

2. Set the resolved path and the explicit ref, then validate the path before
   fetching or writing extractor state:

   ```bash
   repo=/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/<registered-repository>
   expected_ref=version/<approved-version>
   canonical_root=/Users/Shared/Ios/Gimle-Repos/HorizontalSystems

   repo_real=$(realpath "$repo")
   root_real=$(realpath "$canonical_root")
   case "$repo_real" in "$root_real"/*) ;; *)
     echo "STOP: registered repository is outside the canonical Gimle-Repos root" >&2
     exit 1
   esac
   git -C "$repo_real" rev-parse --show-toplevel
   git -C "$repo_real" status --short --branch
   ```

3. Stop if Git reports tracked changes. Untracked generated artifacts, such as
   `scip/`, `.palace/`, `.palace-*`, and `periphery/`, are intentionally kept:

   ```bash
   git -C "$repo_real" diff --quiet && git -C "$repo_real" diff --cached --quiet || {
     echo "STOP: tracked changes must be resolved by the repository owner" >&2
     exit 1
   }
   ```

4. Fetch and fast-forward only to the explicit remote ref. Do not use an
   implicit `git pull`, reset, clean, branch switch, or non-fast-forward merge:

   ```bash
   git -C "$repo_real" fetch origin --prune
   git -C "$repo_real" show-ref --verify --quiet "refs/remotes/origin/$expected_ref" || {
     echo "STOP: expected origin/$expected_ref does not exist" >&2
     exit 1
   }
   git -C "$repo_real" merge --ff-only "origin/$expected_ref"
   git -C "$repo_real" rev-parse HEAD
   ```

   Record the final HEAD together with the slug and ref in the replay log.
   If the merge cannot fast-forward, stop and ask the repository owner which
   branch/ref is intended.

5. Verify SCIP before extractor writes:

   ```bash
   test -s "$repo_real/scip/index.scip" || {
     echo "STOP: SCIP index is missing or empty; build it for this canonical checkout" >&2
     exit 1
   }
   stat -f 'scip_bytes=%z mtime=%Sm' -t '%Y-%m-%dT%H:%M:%S%z' \
     "$repo_real/scip/index.scip"
   ```

   Rebuild SCIP when the source revision advanced or the existing index is not
   known to match that revision. For Xcode apps, use the app-specific emitter
   from [the Xcode app ingestion runbook](xcode-app-ingest.md) before replay.
   Do not point Palace at a SCIP file from another clone.

## Replay extractors

Call the registered project through the native MCP endpoint. For a Swift kit,
start with the idempotent incremental set:

```text
palace.ingest.run_extractor(name="git_history", project="<slug>")
palace.ingest.run_extractor(name="symbol_index_swift", project="<slug>")
palace.ingest.run_extractor(name="code_ownership", project="<slug>")
palace.ingest.run_extractor(name="public_api_surface", project="<slug>")
```

Run any additional extractor required by that project's registered framework
and artifact contract. Xcode applications use the full app extractor set after
their SCIP emitter completes; see [the Xcode app ingestion runbook](xcode-app-ingest.md).
Record each tool response, including skips and missing-input failures. A skip
that says its durable baseline matches the current HEAD is a successful
incremental no-op.

`Project.indexed_commit=null` is only a project-summary projection warning. It
does **not** prove that the extractor-level baseline is absent and must not by
itself trigger `palace.project.analyze` in full mode. Use the extractor result
and its durable checkpoint message to determine whether replay was incremental.

## Stop conditions

Stop rather than guessing or deleting data when any of these is true:

- The registry path differs from the canonical checkout, or resolves outside
  the canonical root.
- The canonical copy has tracked edits, the explicit remote ref is absent, or
  Git cannot fast-forward.
- SCIP is missing, empty, or belongs to a different source copy/revision.
- A registered mapping is stale. `component-kit` is a known example: its
  registered path and the canonical `ComponentKit.Swift` checkout differ, and
  the canonical copy needs SCIP before replay. Repair the mapping and build
  SCIP in a separate operational change first.

After a stop, preserve the checkout and generated artifacts. Record the
observed path, ref, HEAD, and tool response so the owner can repair the source
or registration safely.
