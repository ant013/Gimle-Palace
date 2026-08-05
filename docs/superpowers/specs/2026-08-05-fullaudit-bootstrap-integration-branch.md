# fullAudit: manifest-derived integration branch для runtime Git workspaces

Основание: `origin/develop` на `0dc140978e480fcad893f8e5ae7c5a0eba7620e6`.

## Контекст и воспроизведение

После merge PR #543 bootstrap был запущен на iMac из чистого Git bundle этого
SHA. Он успешно проверил manifest, journal и уже существующую fullAudit
компанию, затем остановился до PATCH конфигурации первого агента:

```text
paperclips/scripts/bootstrap-project.sh: line 544: integration_branch: unbound variable
```

PR #542 добавил `git clone --branch "$integration_branch"` для isolated
runtime workspace, но переменная не была инициализирована. fullAudit уже
декларирует `project.integration_branch: main`, а iMac trusted
`agent_source_root` содержит local `main`, поэтому источник branch определён
manifest-ом и не требует host workaround.

## Цель

Сделать constrained per-agent Git workspace bootstrap самодостаточным:
один раз прочитать и валидировать `project.integration_branch` до hire loop,
чтобы `git clone --branch` использовал объявленный branch без зависимости от
окружения вызывающего shell.

## Допущения

- Каждый v2 project manifest задаёт `project.integration_branch`; fullAudit
  использует `main`.
- `workspace_git_source_path_key` остаётся opt-in и пользовательский
  `agent_source_root` — доверенный Git worktree с этим branch.
- Неуспешный iMac bootstrap не изменил agent config: он остановился на первом
  агенте до создания payload/PATCH. Journal сохранён как evidence.

## Scope

1. В `bootstrap-project.sh` перед циклом найма извлечь
   `project.integration_branch` из manifest, отказавшись от пустого,
   `null` или невалидного Git branch name.
2. Сохранить существующую команду `git clone --branch "$integration_branch"`
   и весь current constrained-CWD lifecycle без новых variables, fallback
   branch или изменения host paths.
3. Дополнить targeted fullAudit assembly test, который фиксирует
   manifest-derived assignment и fail-closed validation до clone use.

## Не входит в scope

- Изменение fullAudit manifest (`main` уже верен), overlays, profiles,
  shared fragments, Git policies, MCP expectations или bypass setting.
- Передача `integration_branch` через environment, изменение iMac source
  checkout либо синхронизация `runs/`/`reports/`.
- Создание roadmap issue или запуск следующего кита до зелёного full smoke.

## Выбранный аналог и дельта

| Срез | Аналог | Инвариант | Дельта | Отклонено |
|---|---|---|---|---|
| S-001 branch lifecycle | `bootstrap-project.sh:300-544` | Manifest уже доступен до agent loop; per-agent clone строится только для opt-in workspace | Прочитать и Git-валидировать branch ровно один раз до loop | Внешняя переменная `integration_branch`: обходит `nounset`, но делает bootstrap зависимым от caller shell |
| S-001 contract | `fullaudit/paperclip-agent-assembly.yaml:3-10` | Project owner определяет integration branch в manifest | Использовать существующее `main` без изменения manifest | Hardcode `main` в shared bootstrap: сломает проекты с `develop` |

## Затрагиваемые области

- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/tests/test_fullaudit_assembly.py`

## Критерии приёмки

1. `bash paperclips/scripts/bootstrap-project.sh fullaudit` больше не падает с
   `integration_branch: unbound variable`; branch берётся из manifest.
2. Пустой/`null`/невалидный branch завершается до clone понятной fail-closed
   ошибкой, без удаления workspace и без изменения agent config.
3. Existing isolated CWD, managed individual `AGENTS.md`, canonical-state
   overlay и bypass contract не меняются.
4. После merge iMac bootstrap из clean bundle проходит stage 1–13, API
   показывает восемь distinct Git CWD и индивидуальные headings; затем ровно
   один `smoke-test.sh fullaudit --cleanup-issues` проходит stage 1–7.
5. Только после зелёного smoke создаётся CEO roadmap/запускается следующий
   kit.

## План проверки до кода

1. Targeted test сначала должен фиксировать отсутствие assignment/validation,
   затем требовать manifest-derived variable до clone command.
2. `bash -n paperclips/scripts/bootstrap-project.sh`.
3. `python3 -m pytest paperclips/tests/test_fullaudit_assembly.py
   paperclips/tests/test_phase_c_smoke_test.py
   paperclips/tests/test_phase_c_smoke_probes.py -v`.
4. `bash paperclips/build.sh --project fullaudit --target codex` и
   `bash paperclips/scripts/validate-manifest.sh fullaudit`.
5. После merge: iMac clean-bundle bootstrap, authenticated API check CWD and
   headings, one full smoke. Credentials остаются в approved `.env` и не
   выводятся.

## Adversarial review

- **Риск hardcode:** разные projects имеют `main` или `develop`; берём branch
  только из manifest.
- **Риск silent fallback:** default branch может создать checkout не той
  ревизии; пустое/невалидное значение fail closed.
- **Риск scope drift:** изменение не касается overlay и canonical state, а
  только исправляет их prerequisite — создание isolated CWD.
- **Риск преждевременной операции:** iMac reproduction остановилась до PATCH
  agent config; повторный bootstrap остаётся idempotent journaled workflow.
- **Меньшая альтернатива:** экспортировать shell variable только в deploy
  команде. Отклонено: не исправляет generic bootstrap и снова сломается при
  следующем штатном запуске.

## Открытые вопросы

Нет блокирующих. Результат полного runtime smoke после merge остаётся
обязательным; при новом провале будет оформлена следующая узкая revision, а не
ослаблены проверки.
