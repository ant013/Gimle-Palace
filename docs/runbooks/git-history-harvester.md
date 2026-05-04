# Runbook: git_history Extractor (GIM-186)

## Обзор

Экстрактор `git_history` обходит git commit history (pygit2, Phase 1) и данные GitHub PR/комментариев (GraphQL, Phase 2). Результаты пишутся в Neo4j (`:Commit`, `:Author`, `:PR`, `:PRComment`, `:File`) и в отдельный Tantivy-индекс `git_history`.

Является фундаментом для 6 исторических экстракторов (#11, #12, #26, #32, #43, #44).

---

## Однократная настройка

### 1. Переменные окружения

Добавить в `.env` (опционально — только Phase 2):

```bash
PALACE_GITHUB_TOKEN=ghp_...    # PAT с правами repo:read
PALACE_GIT_HISTORY_MAX_COMMITS_PER_RUN=50000
PALACE_GIT_HISTORY_TANTIVY_INDEX_PATH=/var/lib/palace/tantivy/git_history
```

Перезапустить `palace-mcp` после изменения `.env`:

```bash
bash paperclips/scripts/imac-deploy.sh
```

### 2. Проверка регистрации экстрактора

```
palace.ingest.list_extractors()
```

В ответе должен быть `"git_history"`.

---

## Первый запуск (полный ingest)

```
palace.ingest.run_extractor(name="git_history", project="gimle")
```

Ожидаемый ответ:

```json
{"ok": true, "run_id": "...", "extractor": "git_history",
 "nodes_written": N, "edges_written": M, "duration_ms": ...}
```

Phase 1 обходит все коммиты от HEAD назад. Phase 2 (если задан `PALACE_GITHUB_TOKEN`) — все PR/комментарии.

---

## Инкрементальное обновление

Повторный вызов:

```
palace.ingest.run_extractor(name="git_history", project="gimle")
```

Экстрактор читает `:GitHistoryCheckpoint` и обходит только новые коммиты / PR обновлённые после последнего checkpoint. `nodes_written` должен быть ≈0 если новых данных нет.

---

## Восстановление после force-push (resync)

Если checkpoint содержит SHA, которого нет в репозитории (force-push переписал историю), экстрактор автоматически делает полный re-walk:

```
[WARNING] git_history_resync_full last_commit_sha_attempted=<old_sha>
```

После успешного прохода checkpoint обновляется на новый HEAD SHA. Действий от оператора не требуется.

---

## Настройка bot-паттернов

По умолчанию детектируются: `github-actions[bot]`, `dependabot[bot]`, `renovate[bot]`, `paperclip-bot`.

Добавить кастомные паттерны через env:

```bash
PALACE_GIT_HISTORY_BOT_PATTERNS_JSON='["my-bot@company.com", "deploy-bot"]'
```

---

## Smoke-тест

```bash
uv run python services/palace-mcp/scripts/smoke_git_history.py
```

Требует работающий palace-mcp на `localhost:8000`.

---

## Запросы для проверки данных в Neo4j

```cypher
// Количество коммитов
MATCH (c:Commit {project_id: 'project/gimle'}) RETURN count(c)

// Авторы (включая ботов)
MATCH (a:Author {project_id: 'project/gimle'})
RETURN a.identity_key, a.is_bot, a.first_seen_at ORDER BY a.first_seen_at

// Checkpoint
MATCH (c:GitHistoryCheckpoint {project_id: 'project/gimle'}) RETURN c

// PR + комментарии
MATCH (p:PR {project_id: 'project/gimle'}) RETURN count(p)
MATCH (c:PRComment {project_id: 'project/gimle'}) RETURN count(c)
```

---

## Очистка

```cypher
// Удалить все данные git_history для проекта
MATCH (n)
WHERE n.project_id = 'project/gimle'
  AND any(label IN labels(n) WHERE label IN ['Commit', 'Author', 'PR', 'PRComment', 'File', 'GitHistoryCheckpoint'])
DETACH DELETE n
```

Удалить Tantivy-индекс:

```bash
docker exec palace-mcp rm -rf /var/lib/palace/tantivy/git_history
```

---

## Связанные документы

- Спецификация: `docs/superpowers/specs/2026-05-01-git-history-harvester-spec-rev2.md`
- Код: `services/palace-mcp/src/palace_mcp/extractors/git_history/`
- Тесты: `services/palace-mcp/tests/extractors/unit/test_git_history_*.py`
- Интеграционные тесты: `tests/extractors/integration/test_git_history_integration.py`
