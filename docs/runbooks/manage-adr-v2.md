# Runbook: `palace.code.manage_adr` v2 (GIM-274)

## Назначение

`palace.code.manage_adr` — нативный MCP-инструмент для чтения, записи,
поиска и управления жизненным циклом ADR-документов (Architecture Decision
Records). ADR хранятся как Markdown-файлы в `docs/postulates/` с проекцией
в граф Neo4j.

**Принципы:**
- Файл — источник истины (AD-D1). Neo4j — слой проекции.
- 6-секционный формат: PURPOSE, STACK, ARCHITECTURE, PATTERNS, TRADEOFFS, PHILOSOPHY.
- Нативная регистрация `@mcp.tool`, не CM subprocess (AD-D7).
- Идемпотентная запись через SHA-256 хеш тела секции.
- `fcntl.flock` — файловая блокировка для параллельных записей (AD-D9).

---

## Поверхность инструмента (4 режима)

### `read(slug)`

Читает файл `docs/postulates/<slug>.md`, парсит заголовок и 6 секций,
проецирует в граф (`:AdrDocument` + `:AdrSection`).

```json
{
  "mode": "read",
  "slug": "gimle-architecture"
}
```

Ответ:
```json
{
  "ok": true,
  "slug": "gimle-architecture",
  "title": "Gimle Architecture",
  "body": "# Gimle Architecture\n\n## PURPOSE\n...",
  "sections": [
    {"name": "PURPOSE", "body": "...", "body_hash": "abc123..."}
  ]
}
```

Ошибки: `adr_not_found`, `invalid_slug`.

---

### `write(slug, section, body, decision_id?)`

Идемпотентно записывает секцию ADR-файла. Создаёт файл если не существует.
Обновляет `:AdrSection` в Neo4j. Если передан `decision_id`, создаёт ребро
`(:Decision)-[:CITED_BY]->(:AdrDocument)`.

```json
{
  "mode": "write",
  "slug": "gimle-architecture",
  "section": "PURPOSE",
  "body": "Gimle — palace of knowledge...",
  "decision_id": "d9f7a3b2-1234-5678-abcd-ef0123456789"
}
```

Ответ:
```json
{
  "ok": true,
  "slug": "gimle-architecture",
  "section": "PURPOSE",
  "written": true
}
```

`written: false` — если тело не изменилось (хеш совпал), файл не перезаписывался.

Ошибки: `invalid_slug`, `invalid_section`, `decision_not_found`.

---

### `supersede(old_slug, new_slug, reason)`

Помечает старый ADR как superseded: добавляет баннер в файл, обновляет
`old.status = "superseded"` в графе, создаёт ребро
`(:AdrDocument {slug:old})-[:SUPERSEDED_BY {reason, ts}]->(:AdrDocument {slug:new})`.

Операция идемпотентна: повторный вызов не дублирует баннер.

```json
{
  "mode": "supersede",
  "old_slug": "gimle-auth-v1",
  "new_slug": "gimle-auth-v2",
  "reason": "Migrate from session tokens to JWT (GIM-201)."
}
```

Ответ:
```json
{
  "ok": true,
  "old_slug": "gimle-auth-v1",
  "new_slug": "gimle-auth-v2"
}
```

Ошибки: `adr_not_found` (старый файл не найден), `invalid_slug`.

---

### `query(keyword?, section_filter?, project_filter?)`

Граф-поиск по ADR через Cypher (AD-D6: Cypher-only, не Tantivy —
корпус ADR мал, ранжирование не нужно).

- `keyword` — `body_excerpt CONTAINS keyword` (case-sensitive)
- `section_filter` — ограничить результаты одной секцией (напр. `"ARCHITECTURE"`)
- `project_filter` — prefix-фильтр по slug (напр. `"gimle-"`)
- Исключает ADR со статусом `superseded`
- LIMIT 200

```json
{
  "mode": "query",
  "keyword": "Neo4j",
  "section_filter": "ARCHITECTURE",
  "project_filter": "gimle-"
}
```

Ответ:
```json
{
  "ok": true,
  "results": [
    {
      "slug": "gimle-architecture",
      "section_name": "ARCHITECTURE",
      "body_excerpt": "...Neo4j stores the graph..."
    }
  ],
  "count": 1
}
```

---

## 6-секционный формат ADR

Каждый ADR-файл должен содержать ровно 6 секций в этом порядке:

```markdown
# <Заголовок>

## PURPOSE
Зачем этот ADR. Контекст, проблема, мотивация.

## STACK
Выбранный технологический стек.

## ARCHITECTURE
Структурные решения. Компоненты, связи.

## PATTERNS
Паттерны проектирования. Конвенции.

## TRADEOFFS
Компромиссы. Что теряем, что получаем.

## PHILOSOPHY
Принципы и ценности за этим решением.
```

`write` может записывать любую секцию независимо — остальные сохраняются.
`read` парсит только секции с каноническими именами; нестандартные игнорируются.

---

## Дрейф файла и графа

### Вызывающий дрейф

Если файл `docs/postulates/<slug>.md` был отредактирован вручную (git commit,
текстовый редактор и т.д.) без вызова `manage_adr`, граф может стать неактуальным.

### Восстановление

Вызов `read(slug)` всегда перепроецирует файл в граф — это идемпотентная операция.
Достаточно вызвать `read` для каждого изменённого ADR чтобы граф догнал файл.

```bash
# Проверить актуальность в Neo4j
MATCH (d:AdrDocument {slug: "gimle-architecture"})-[:HAS_SECTION]->(s:AdrSection)
RETURN d.slug, s.section_name, s.body_excerpt
```

### Инвариант

`body_excerpt` в `:AdrSection` = первые 500 символов `body` секции.
Если `body_excerpt` в графе ≠ содержимому файла — вызвать `read(slug)`.

---

## Decision bridge

`write` с параметром `decision_id` создаёт ребро
`(:Decision {id})-[:CITED_BY]->(:AdrDocument {slug})`.

Это позволяет связывать структурированные решения (`palace.memory.decide`)
с документирующими их ADR.

**Важно:** `decision_id` должен ссылаться на существующий узел `:Decision` в графе.
Если узел не найден — `write` вернёт `error_code: "decision_not_found"` и файл
не будет изменён.

```cypher
# Проверить связи ADR ↔ Decision
MATCH (d:Decision)-[:CITED_BY]->(a:AdrDocument)
RETURN d.id, d.title, a.slug
```

---

## Диагностика

### Инструмент недоступен

```
palace.code.manage_adr → {"ok": false, "error_code": "driver_unavailable"}
```
Neo4j driver не инициализирован. Проверить `palace.memory.health()`.

### ADR не найден

```json
{"ok": false, "error_code": "adr_not_found", "message": "..."}
```
Файл `docs/postulates/<slug>.md` не существует в `PALACE_ADR_BASE_DIR`.

### Нет графовых данных после записи

Проверить что `ensure_adr_schema` выполнился при старте сервера:
```cypher
SHOW CONSTRAINTS WHERE name STARTS WITH 'adr_'
```

Если ограничений нет — выполнить `docker compose restart palace-mcp`.

### Env-переменные

| Переменная | Дефолт | Описание |
|---|---|---|
| `PALACE_ADR_BASE_DIR` | `docs/postulates` | Корень ADR-файлов (относительно cwd контейнера) |

---

## Дымовой тест (iMac)

```bash
# 1. Записать тестовый ADR
mcp call palace.code.manage_adr \
  '{"mode":"write","slug":"test-e5-smoke","section":"PURPOSE","body":"Smoke test."}'

# 2. Прочитать обратно
mcp call palace.code.manage_adr \
  '{"mode":"read","slug":"test-e5-smoke"}'

# 3. Поиск по ключевому слову
mcp call palace.code.manage_adr \
  '{"mode":"query","keyword":"Smoke test"}'

# 4. Supersede
mcp call palace.code.manage_adr \
  '{"mode":"write","slug":"test-e5-new","section":"PURPOSE","body":"New version."}'
mcp call palace.code.manage_adr \
  '{"mode":"supersede","old_slug":"test-e5-smoke","new_slug":"test-e5-new","reason":"Smoke cleanup."}'

# 5. Проверить граф
cypher-shell -u neo4j "MATCH (d:AdrDocument)-[:HAS_SECTION]->(s) RETURN d.slug, count(s)"

# 6. Очистить тестовые файлы
rm docs/postulates/test-e5-smoke.md docs/postulates/test-e5-new.md
cypher-shell -u neo4j "MATCH (d:AdrDocument) WHERE d.slug STARTS WITH 'test-e5' DETACH DELETE d"
```
