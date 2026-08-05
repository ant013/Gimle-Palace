# fullAudit: изоляция runtime cwd и agent bundles

Основание: `origin/develop` на `91f8f788726adf410fee243a5a1dd8155be40274`.

## Контекст и наблюдаемая неисправность

Полный iMac smoke от `2026-08-05T12:48:04Z` прошёл инфраструктурные шаги 1–4,
но провалил stage 5. Проверка live bundle через Paperclip API установила, что
CEO, CTO, Swift-аудитор, Publisher и QA получили один и тот же `# FullAudit QA`
вместо собственных собранных ролей. Это объясняет несоответствия Git и фазовой
ответственности: локальный builder создаёт разные файлы, но все runtime-агенты
читают `AGENTS.md` из общего Git cwd `agent_source_root`.

## Цель

Сделать runtime cwd каждого fullAudit-агента отдельным доверенным Git workspace,
чтобы его `AGENTS.md` не мог быть перезаписан деплоем другого агента. После
повторного bootstrap все восемь agent bundles должны соответствовать своим
profile → role_source → project overlay, а полный smoke должен дойти до stage 7.

## Допущения

- `agent_source_root` на iMac остаётся доверенным Git-источником для подготовки
  отдельных agent workspaces; значения секретов не читаются и не попадают в
  код, отчёты или логи.
- Существующий `team_workspace_root/<Agent>/workspace` — управляемая область
  fullAudit. Если в ней есть непредусмотренные пользовательские файлы или
  невалидный Git checkout, bootstrap обязан остановиться, а не удалять их.
- Ошибки 500 при удалении уже завершённых disposable smoke issues — отдельный
  дефект Paperclip API. В рамках этой правки они остаются `done`; повторного
  удаления широким запросом не будет.

## Scope

1. Добавить в manifest fullAudit явный opt-in для подготовки per-agent Git cwd
   из доверенного host-local source path; удалить использование общего
   `agent_cwd_path_key` как cwd всех агентов.
2. В `bootstrap-project.sh` подготовить такой workspace до создания/patch
   `adapterConfig`: безопасно и идемпотентно создать либо проверить отдельный
   Git checkout каждого агента, назначить его `cwd`, а затем положить туда
   именно его собранный `AGENTS.md`.
3. Сохранить constrained roots, `PAPERCLIP_API_URL` loopback и уже одобренный
   `dangerouslyBypassApprovalsAndSandbox`; не возвращать `--skip-git-repo-check`.
4. Добавить узкие tests, доказывающие: общий source cwd не назначается;
   per-agent cwd различаются, являются Git worktree и получают разные bundles;
   bootstrap отказывает при неуправляемом занятом workspace.

## Не входит в scope

- Изменение shared profiles/fragments, role_source файлов или workflow_role.
- Ролевые исключения для Git, ослабление проверок smoke либо подмена их
  ожидаемых маркеров.
- Перезапуск BitcoinCore.Swift или создание roadmap issue до зелёного smoke.
- Исправление server-side HTTP 500 на DELETE issue.

## Выбранный аналог и дельта

| Срез | Опорный аналог | Сохраняемый инвариант | Новая дельта | Отклонённый вариант |
|---|---|---|---|---|
| S-001 runtime-инструкции | `bootstrap-project.sh` workspace lifecycle | Каждый агент работает из собственного workspace, а builder уже создаёт отдельный bundle | Подготовить Git cwd до adapter config и копировать bundle в этот cwd | Общий `agent_source_root`: он доказанно сделал QA bundle общим для всех |
| S-001 композиция | ThorChain manifest + `compose_agent_prompt.py` | Три слоя: shared profile → role craft → project overlay; `workflow_role` отдельный | Не менять слои, а восстановить их доставку конкретному агенту | Добавить fullAudit-specific Git правила или переписать profiles |

## Затрагиваемые области

- `paperclips/projects/fullaudit/paperclip-agent-assembly.yaml`
- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/tests/test_fullaudit_assembly.py`
- новый/существующий узкий bootstrap test, если текущий fixture не может
  смоделировать Git workspace безопасно.

## Критерии приёмки

1. В live configuration iMac `adapterConfig.cwd` для всех восьми fullAudit
   agents различается и указывает на Git worktree под team workspace root.
2. API bundle каждого агента содержит собственный role heading: CEO, CTO,
   auditor/verifier, publisher или QA — и Publisher больше не получает QA
   правила.
3. Stage 5 full smoke проходит профильные MCP/Git/handoff/phase probes без
   ослабления ожиданий; stage 7 проходит E2E handoff.
4. Все disposable smoke issues после прогона имеют `done` или удалены; никакая
   бизнес-задача не создаётся до успеха smoke.
5. Существующие manifest/build checks сохраняются зелёными.

## План проверки до кода

1. Red test: смоделировать manifest opt-in и убедиться, что bootstrap не
   использует один `agent_source_root` как cwd нескольких агентов.
2. Unit/script test: два agents получают различные подготовленные Git cwd и
   соответствующие каждому `AGENTS.md`; занятой неуправляемый каталог вызывает
   отказ без удаления файлов.
3. `bash -n paperclips/scripts/bootstrap-project.sh`.
4. `python3 -m pytest paperclips/tests/test_fullaudit_assembly.py` плюс
   точечный bootstrap/smoke test и manifest validator.
5. После merge: bootstrap fullAudit на iMac, проверить CWD и bundle headings
   через authenticated Paperclip API, затем один полный
   `smoke-test.sh fullaudit --cleanup-issues`.

## Adversarial review

- **Риск общей базы:** отдельные cwd необходимы именно потому, что managed
  `AGENTS.md` materializes в cwd; оставление общего Git checkout снова даст
  last-writer-wins. Решение: один managed Git cwd на agent.
- **Риск потери audit state:** workspaces не заменяют `project_root` как
  authoritative state; правка меняет carrier инструкций/runtime cwd и не
  переносит `runs/`, `reports/` или read-only kit clones.
- **Риск широкого framework refactor:** opt-in ограничивается manifest fullAudit
  и существующим bootstrap lifecycle; profiles, ThorChain и остальные проекты
  не меняются.
- **Риск destructive setup:** bootstrap принимает только пустой либо ранее
  распознанный управляемый workspace; иначе fail closed.
- **Меньшая альтернатива (сменить smoke ожидания):** отвергнута — live bundles
  фактически неверны, а не только проверка.

## Открытые вопросы

Нет блокирующих: конкретный source path уже присутствует в iMac `paths.yaml` и
является Git checkout. Реализация должна подтвердить его remote/branch только
метаданными, без вывода credential URL.
