# Code Ownership Mini Fixture

## Layout

- 3 authors:
  - `Anton S <old@example.com>` — also writes as `Anton Stavnichiy <new@example.com>` (mailmapped)
  - `Other Human <other@example.com>` — single identity
  - `dependabot[bot] <bot@example.com>` — bot author
- 5 files:
  - `apps/main.py` — modified by both Anton (under both emails) and Other Human
  - `apps/util.py` — created and only touched by Other Human
  - `apps/legacy.py` — created and modified by Anton, then `git rm`-ed in HEAD
  - `apps/binary.png` — binary content; blame must skip
  - `apps/merge_target.py` — content changed only via merge commit
- `.mailmap` mapping `old@example.com → new@example.com` for Anton
- 11 commits including 1 merge

## Regenerate

```bash
bash services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh
```

Idempotent — wipes existing fixture, rebuilds bit-exactly.
