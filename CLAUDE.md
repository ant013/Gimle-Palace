# Gimle Palace — Developer Guide

## Branch Flow

```
feature/* → develop (PR, CodeReviewer sign-off required)
develop → main (release PR, CTO approval required)
```

**Rules:**
- All work in feature branches cut from `develop`: `git checkout -b feature/ISSUE-N origin/develop`
- PRs open against `develop`, never `main`
- `main` is updated only via develop→main release PRs
- Force-push to `main`/`develop` is forbidden
- Review pipeline — see `docs/review-flow.md` (Sonnet mechanical pass → Opus architectural pass on feature→develop PRs)

## Docker Compose Profiles

Services use explicit profile opt-in. Start with one of:

```bash
docker compose --profile review up -d    # review mode (palace-mcp + neo4j)
docker compose --profile analyze up -d  # analyze mode
docker compose --profile full up -d     # full mode
```

No profile → no services start (expected behaviour — enforce explicit opt-in).

## Environment

Copy `.env.example` to `.env` and fill real values before running compose.
