# fullAudit: доверенный Git-cwd для runtime-опроса агентов

## Контекст и доказательство

Полный smoke созданной fullAudit-компании остановился на первом runtime probe:
`FullAuditQAEngineer` вернул `Not inside a trusted directory and --skip-git-repo-check was not specified`.
API-конфигурация подтверждает, что все восемь агентов используют пустые
`/Users/Shared/Ios/full-audit-paperclip-runs/<agent>/workspace` как `cwd`.
AGENTS.md, bindings, watchdog и два TOML-субагента уже доставлены.

## Решение

Создать на iMac отдельный чистый Git-checkout fullAudit без `.env`, например
`/Users/Shared/Ios/full-audit-agent-source`, и использовать его как `cwd` каждого
fullAudit-агента. Основной checkout `/Users/Shared/Ios/full-audit` остаётся местом
состояния (`runs/`, `reports/`, `site/dist/`) и не становится cwd агента.

Manifest и bootstrap получают project-scoped настройку trusted agent cwd:

- bootstrap проверяет, что путь существует и является Git worktree;
- constrained sandbox не добавляет этот cwd в writable roots;
- agents получают read-only root чистого checkout и лишь явно разрешённые writable roots
  основного checkout;
- scratch/workspace и AGENTS.md остаются отдельными.

## Объём

- Декларативная настройка и валидация trusted agent cwd для constrained fullAudit.
- Пример host-local paths с ключом clean checkout.
- Узкие тесты: cwd — Git checkout, но не writable root; legacy проекты неизменны.
- На iMac: создать/обновить clean private clone, redeploy существующих agent bindings,
  выполнить полный smoke с удалением disposable issue.

## Не входит

- Создание roadmap или рабочего audit issue.
- Изменение агентских ролей, состава субагентов, серьёзностей и полного audit runbook.
- Предоставление агентам доступа к `.env` или иным секретам.

## Критерии приёмки

1. Все 8 агентов имеют Git-trusted cwd, но writable roots не включают этот cwd.
2. `PAPERCLIP_API_*` отсутствуют в AGENTS.md, report-ах и agent cwd.
3. Полный `smoke-test.sh fullaudit --cleanup-issues` проходит: API, workspaces,
   watchdog, runtime MCP/instruction probes и e2e handoff.
4. Только после успешного smoke допускается создание roadmap issue.

## Проверка

- manifest validator, shell syntax и новый тест;
- CI PR;
- iMac: проверить отсутствие `.env` в clean checkout, agent config, полный smoke.

## Открытый вопрос

Нужен выбор оператора: одобрить отдельный clean checkout как безопасный trusted cwd.
