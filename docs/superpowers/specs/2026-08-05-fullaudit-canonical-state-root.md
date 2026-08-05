# fullAudit: canonical audit state при изолированном runtime cwd

Основание: `origin/develop` на `24c52033b893b8c8e2a2b489251a5196468b518f`
после merge PR #542 (`fix(fullaudit): isolate runtime agent workspaces`).

## Контекст

PR #542 исправляет доказанную доставку инструкций: у каждого fullAudit-агента
будет свой Git runtime cwd и собственный managed `AGENTS.md`. Это устраняет
last-writer-wins, из-за которого CEO, CTO, аудиторы и Publisher получали
`# FullAudit QA`.

При проверке iMac обнаружена следующая граница. `agent_source_root` — отдельный
detached checkout; после bootstrap рабочие cwd агентов являются его отдельными
клонами. В текущем project overlay обычная работа запускает
`python3 bin/next_kit.py` относительным путём. При новом cwd это создало бы
независимые копии `runs/` и `reports/`, хотя RUNBOOK требует единственное
durable state. Canonical checkout iMac для этого state — host-local
`{{paths.project_root}}`; точное значение пути не попадает в repository source.

## Цель

Сохранить unique Git cwd только как carrier индивидуального `AGENTS.md`, а все
обычные операции fullAudit со state выполнять из единственного canonical
`{{paths.project_root}}`.

## Допущения

- `paths.project_root` на iMac указывает на canonical checkout full-audit и
  существует: это уже обязательный constrained host path bootstrap.
- Все операции, изменяющие audit state, предусмотрены RUNBOOK и остаются в
  `{{paths.project_root}}`; клоны аудируемых китов в `workspace/repos/` по-
  прежнему read-only.
- Disposable issues с заголовком ровно `smoke-probe-*` или `smoke-e2e-*` не
  запускают audit-команды и не нуждаются в canonical-root routing.
- Значения host paths и любые секреты не записываются в manifest, тесты,
  отчёты или комментарии.

## Scope

1. Дополнить только fullAudit Codex common overlay явным правилом: у обычного
   audit issue перед чтением `RUNBOOK.md`, запуском `bin/*` или работой с
   `runs/`, `reports/`, `site/` агент переходит в `{{paths.project_root}}`.
2. Ясно назвать этот checkout единственным authority state и запретить считать
   runtime cwd вторым состоянием или синхронизировать между ними результаты.
3. Добавить узкую assembly-проверку, что rendered fullAudit role prompts
   получают resolved canonical-root instruction и сохраняют ранее заданное
   narrow smoke exception.

## Не входит в scope

- Изменение merged CWD-isolation bootstrap, manifest, shared fragments,
  profiles, `role_source`, `workflow_role`, Git-политик или MCP smoke
  ожиданий.
- Копирование/синхронизация `runs/` или `reports/` между agent workspaces.
- Перезапуск `bitcoin-core-swift`, создание CEO roadmap issue либо запуск
  `bitcoin-kit-swift` до успешного полного smoke.
- Исправление server-side HTTP 500 при DELETE уже завершённых disposable
  smoke issues.

## Выбранный аналог и дельта

| Срез | Опорный аналог | Покрытие и инвариант | Требуемая дельта | Отклонённый вариант |
|---|---|---|---|---|
| S-001 canonical audit state | `fullaudit/overlays/codex/_common.md` | Project overlay — третий слой после profile и role_source; его normal-audit правило относится ко всем восьми ролям | Перед относительными audit-командами предписать `cd {{paths.project_root}}`; назвать его единственным state authority | Оставить относительные команды: после per-agent cwd они расходятся в разные `runs/` и `reports/` |
| S-001 host-path lifecycle | `bootstrap-project.sh:521-576` | `project_root` уже обязательный constrained host path, источник writable paths и `workspace/repos`; unique runtime cwd сохраняется для bundle isolation | Bootstrap не менять | Вернуть shared `agent_source_root` как cwd: вновь даст общий last-writer-wins `AGENTS.md` |

## Затрагиваемые области

- `paperclips/projects/fullaudit/overlays/codex/_common.md`
- `paperclips/tests/test_fullaudit_assembly.py`

## Критерии приёмки

1. Каждый rendered fullAudit Codex prompt содержит resolved instruction,
   направляющий normal audit work в canonical `project_root`; в rendered files
   не остаётся `{{...}}` template.
2. Disposable smoke probes по-прежнему ничего не читают, не меняют и не
   запускают из audit state.
3. Bootstrap по PR #542 продолжает назначать восемь разных Git runtime cwd и
   раздельные role bundles; новая правка не меняет этот lifecycle.
4. На iMac после merge и bootstrap один полный
   `smoke-test.sh fullaudit --cleanup-issues` подтверждает корректные bundle
   headings, CWD isolation, MCP/Git/handoff/phase probes и E2E handoff без
   ослабления проверок. Если server-side DELETE для завершённого disposable
   issue снова вернёт 500, issue должен быть `done`, а дефект фиксируется как
   ограничение, без широкого повторного удаления.
5. До зелёного smoke не создаётся roadmap issue и не запускается следующий
   аудитный кит.

## План проверки до кода

1. Обновить существующий assembly test так, чтобы он сначала не проходил без
   canonical-root instruction, затем проверял common overlay и все rendered
   fullAudit prompts на resolved path и отсутствие `{{`.
2. `bash paperclips/build.sh --project fullaudit --target codex`.
3. `bash paperclips/scripts/validate-manifest.sh fullaudit`.
4. `python3 -m pytest paperclips/tests/test_fullaudit_assembly.py
   paperclips/tests/test_phase_c_smoke_test.py
   paperclips/tests/test_phase_c_smoke_probes.py -v`.
5. `bash -n paperclips/scripts/bootstrap-project.sh
   paperclips/scripts/smoke-test.sh`.
6. После merge — bootstrap из чистого temporary clone на iMac, authenticated
   API check восьми distinct CWD и individual role headings, затем ровно один
   full smoke. Значения auth/env не выводятся.

## Adversarial review

- **Конфликт CWD и state:** unique CWD необходим для managed bundle, но не
  может быть durable state. Решение: overlay направляет normal audit work в
  canonical root, не отменяя unique cwd.
- **Риск широкого framework change:** затрагивается один project overlay и
  один targeted regression test; bootstrap и shared fragments не меняются.
- **Риск обхода smoke:** smoke исключение остаётся строго по префиксу
  заголовка и по-прежнему запрещает файловые/audit действия.
- **Риск ошибочного host path:** templating разрешает `paths.project_root` из
  host-local paths; build и iMac live smoke докажут resolved value, но не
  публикуют его.
- **Меньшая альтернатива — копировать state после каждой задачи:** отвергнута:
  добавляет гонки, два источника истины и противоречит RUNBOOK.

## Открытые вопросы

Нет блокирующих. Полный smoke после merge остаётся необходимой live
проверкой; его фактические MCP-результаты определят, требуется ли отдельная
минимальная правка для доступности инструментов.
