# git-history-mini-project fixture

## How to regenerate

```bash
bash regen.sh
```

Run from any directory — the script resolves paths via `git rev-parse`.

## Synthetic repo content

5 commits, 2 authors:

1. **Initial commit** — `foo@example.com` (Foo Human)
2. **Add file2.txt** — `github-actions[bot]@users.noreply.github.com` (bot)
3. **Add file3.txt on topic** — `foo@example.com` (human, topic branch tip)
4. **Merge branch 'topic'** — `foo@example.com` (merge commit, 2 parents: c2 + c3)
5. **Final commit** — `foo@example.com` (human)

The repo validates:
- `is_merge` detection (commit 4 has 2 parents)
- Bot detection via `[bot]@users.noreply.github.com` email
- Incremental walk (walk_since HEAD sha → 0 new commits)

## GraphQL fixtures

| File | Purpose |
|------|---------|
| `github_responses/prs_page_1.json` | 2 PRs: 1 with comment, 1 with null author (Mannequin shape) |
| `github_responses/pr_comments_inner_pagination.json` | PR with `comments.pageInfo.hasNextPage: true` |
| `github_responses/rate_limit_low.json` | `rateLimit.remaining: 50` → triggers `RateLimitExhausted` |

Fixtures hand-crafted 2026-05-04 following GitHub GraphQL schema
(no live API call needed; shapes verified against `github_client.py` field access paths).
