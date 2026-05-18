# GIM-348: Extractor framework — shared stop-list for build/dependency dirs

**Date:** 2026-05-18
**Issue:** GIM-348
**Owner:** CTO (plan) -> MCPEngineer (impl) -> CR -> OpusArchitectReviewer -> QA -> CTO (merge)

## Problem

4 of 7 extractors failed during the GIM-334 BitcoinCore smoke run because
walkers descend into SPM dependency / build artifact directories
(`.build/checkouts/` contains ~200K Swift LOC of GRDB, Alamofire, swift-nio-ssl,
etc.). Each extractor re-invents (or omits) directory exclusion logic.

| Extractor | Symptom | Root cause |
|---|---|---|
| `code_ownership` | timeout 300s | pygit2 blame walks `.build/checkouts/` |
| `crypto_domain_model` | timeout 300s | semgrep scans `.build/checkouts/` |
| `hotspot` | timeout 300s | lizard ccn walks `.build/checkouts/` |
| `error_handling_policy` | `IsADirectoryError` | `rglob` yields dir + no `is_file()` guard |

## Design

### New module: `extractors/foundation/walk.py`

Two public symbols:

1. **`DEFAULT_STOP_DIRS`** — `frozenset[str]` of directory names to prune:
   `.build`, `.git`, `node_modules`, `vendor`, `Pods`, `Carthage`,
   `__pycache__`, `target`, `.venv`, `.gradle`, `.kotlin`, `.idea`,
   `build`, `dist`, `.pytest_cache`, `.mypy_cache`, `.tantivy`,
   `__MACOSX`, `DerivedData`, `SourcePackages`, `.swiftpm`.

2. **`DEFAULT_STOP_PREFIXES`** — `tuple[str, ...]` for prefix-matched dirs:
   `.palace-xcb-`, `.palace-scip-`.

Two public functions:

3. **`should_skip_path(parts, *, extra_excludes, extra_prefixes) -> bool`**
   — predicate on path-part tuple. For use by walkers that don't use `os.walk`
   (e.g., pygit2 tree traversal in `code_ownership`).

4. **`walk_repo(root, *, suffixes, extra_excludes, extra_prefixes) -> Iterator[Path]`**
   — `os.walk`-based generator with in-place `dirnames[:]` pruning (never
   descends into excluded dirs). Optional `suffixes` filter. Yields only
   regular files (`is_file()` guard built-in).

### Why `os.walk` over `rglob`

`Path.rglob` descends into all directories first, then filters. `os.walk`
with `dirnames[:]` pruning skips excluded subtrees entirely — O(relevant
files) not O(all files). Critical when `.build/checkouts/` has 200K+ files.

## Steps

### Step 1 — Create `foundation/walk.py`

- **File:** `services/palace-mcp/src/palace_mcp/extractors/foundation/walk.py`
- **What:** Implement `DEFAULT_STOP_DIRS`, `DEFAULT_STOP_PREFIXES`,
  `should_skip_path()`, `walk_repo()` as described above.
- **Export:** Add to `foundation/__init__.py`.
- **Owner:** MCPEngineer
- **Acceptance:** Unit tests pass (step 6).

### Step 2 — Switch `hotspot/file_walker.py`

- **File:** `services/palace-mcp/src/palace_mcp/extractors/hotspot/file_walker.py`
- **What:** Replace local `_STOP_DIRS` with `walk_repo(root, suffixes=_LIZARD_EXTENSIONS)`.
  Keep `_FIXTURE_STOP_PARTS` as a local post-filter (extractor-specific logic).
- **Owner:** MCPEngineer
- **Acceptance:** Existing hotspot tests pass. `.build/` pruned before descent.

### Step 3 — Filter `code_ownership/extractor.py`

- **File:** `services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py`
- **What:** In `_all_files_in_head()`, add `should_skip_path(full.split('/'))` check
  in the `visit()` tree walker. When a tree entry name matches stop-dirs, skip the
  entire subtree (don't recurse into it).
- **Owner:** MCPEngineer
- **Acceptance:** Existing code_ownership tests pass. `.build/checkouts/` files
  excluded from blame set.

### Step 4 — Filter `crypto_domain_model/extractor.py`

- **File:** `services/palace-mcp/src/palace_mcp/extractors/crypto_domain_model/extractor.py`
- **What:** In `_semgrep_target_batches()`, replace `target.rglob("*.swift")` with
  `walk_repo(target, suffixes=frozenset({".swift"}))`.
- **Owner:** MCPEngineer
- **Acceptance:** Existing crypto_domain_model tests pass. `.build/` not scanned.

### Step 5 — Fix `error_handling_policy/extractor.py`

- **File:** `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py`
- **What:** In `_collect_catch_sites()`, replace `repo_root.rglob(_SWIFT_GLOB)` with
  `walk_repo(repo_root, suffixes=frozenset({".swift"}))`. Add explicit
  `if not path.is_file(): continue` belt-and-suspenders guard before `read_text()`.
- **Owner:** MCPEngineer
- **Acceptance:** Existing tests pass + regression test (step 7). No `IsADirectoryError`.

### Step 6 — Unit tests for `foundation/walk.py`

- **File:** `services/palace-mcp/tests/extractors/unit/test_walk.py`
- **Tests:**
  - `test_stop_dirs_skipped` — `.build/checkouts/GRDB/X.swift` and
    `node_modules/foo/bar.js` not yielded.
  - `test_source_files_not_skipped` — `Sources/App/Main.swift` yielded.
  - `test_extra_excludes_additive` — custom exclude `MyCache/` also pruned.
  - `test_prefix_matching` — `.palace-xcb-abc123/` skipped.
  - `test_suffixes_filter` — only `.swift` files when `suffixes={".swift"}`.
  - `test_should_skip_path_predicate` — direct predicate tests.
- **Owner:** MCPEngineer
- **Acceptance:** All tests green.

### Step 7 — Regression test for `error_handling_policy`

- **File:** `services/palace-mcp/tests/extractors/unit/test_error_handling_policy_stoplist.py`
- **Test:** Synthetic `tmp_path` fixture with `.build/checkouts/GRDB.swift/` directory
  (name ending in `.swift` that is actually a directory) in walk path. Extractor
  completes without `IsADirectoryError`, returns valid result.
- **Owner:** MCPEngineer
- **Acceptance:** Test green, no raise.

### Step 8 — Runbook documentation

- **File:** `docs/runbooks/extractor-stoplist.md`
- **What:** Document each entry in `DEFAULT_STOP_DIRS` and `DEFAULT_STOP_PREFIXES`
  with rationale (why excluded, what ecosystem it belongs to). Document how to add
  per-extractor custom excludes via `extra_excludes` constructor arg.
- **Owner:** MCPEngineer
- **Acceptance:** File exists, each entry documented.

### Step 9 — Live smoke on `bitcoin-core` reference

- **Owner:** QAEngineer (on iMac)
- **What:** Run `code_ownership`, `crypto_domain_model`, `hotspot`,
  `error_handling_policy` extractors against BitcoinCore.Swift repo.
- **Acceptance:** All 4 complete in <60s each (vs 300s timeout). Reports contain
  real findings (non-empty results).

## Pipeline

```
CTO (this plan) -> CR (plan-first review) -> MCPEngineer (steps 1-8)
-> CR (mechanical review) -> OpusArchitectReviewer (adversarial review)
-> QA (step 9, live smoke) -> CTO (merge)
```

## File-overlap note

Sister issue (Codex team) for `symbol_index_swift counter_state_corrupt` touches
`extractors/foundation/counter.py` + `extractors/symbol_index_swift/` — different
foundation module, no conflict expected with `foundation/walk.py`.
