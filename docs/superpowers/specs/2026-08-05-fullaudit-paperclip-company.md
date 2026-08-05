# Спецификация: компания fullAudit в Paperclip

**Статус:** на ревью — реализация и внешние изменения запрещены до явного одобрения оператора.

**Основание:** `origin/develop` на коммите `0f0a3957db4b6ad94e27a06c2beebc9949510708`; ветка `feature/fullaudit-paperclip-company`.

## 1. Цель

Создать и запустить в Paperclip на iMac отдельную компанию **fullAudit** для непрерывного аудита 32 библиотек HorizontalSystems. Компания должна выполнять один кит за активный дочерний issue, сохранять результат на диске, публиковать валидированный русский отчёт на `report.ant013.work` и только затем брать следующий кит.

Успех — после bootstrap существует отдельная компания с изолированной командой, watchdog и read-only субагентами; smoke-проверка проходит, а родительский issue программы создан и передан CEO для первого кита. Клоны аудитируемых китов никогда не изменяются.

## 2. Проверенный контекст и допущения

- Paperclip API на `paperclip.ant013.work` ответил HTTP 200; iMac, Paperclip, nginx и cloudflared запущены.
- В control-plane уже есть `UnstoppableAudit` (24 агента, 4 routines), но это отдельная PR-delta команда приложения; её нельзя переиспользовать для fullAudit.
- Префикс `FUL` свободен среди текущих префиксов `STA`, `TRD`, `TEL`, `WR`, `MED`, `GIM`, `UNS`.
- Приватный source remote `github.com/ant013/full-audit.git` создан; iMac checkout `/Users/Shared/Ios/full-audit` на ветке `main` проверен на SHA `9b0b3ac3286b3cc21b3de65b59c6e15098735c6d`. В нём нет `.env`, `ops/.env` и клонов китов.
- Модель всех основных агентов и субагентов: `gpt-5.6-sol`, `xhigh`; доменный разбор и верификация — read-only.
- Индексные MCP `codebase-memory`, Serena и Palace не доступны в текущем сеансе проектирования. Аналоги проверены точечным чтением текущего дерева; доверие к индексной части — `YELLOW` и сохранено в `audit/runs/fullaudit-paperclip-company-20260805/`.
- Текущий generic bootstrap передаёт `dangerouslyBypassApprovalsAndSandbox: true`; для команды security-аудита это неприемлемо без отдельной per-project конфигурации ограничений.

## 3. Решение

### 3.1. Отдельный проект и компания

Добавить проект `paperclips/projects/fullaudit/` с манифестом schema v2:

- `display_name: fullAudit`, `system_name: fullAudit`, `issue_prefix: FUL`;
- target — только `codex_local`, managed bundles;
- `host_paths.required_existing` требует checkout fullAudit и каталог Gimle skills;
- host-local `paths.yaml` хранит абсолютные пути и team workspace, поэтому их нет в коммите;
- manifest не хранит UUID, ключи, пути iMac или настройки Telegram.

Компания создаётся только `paperclips/scripts/bootstrap-project.sh fullaudit --config … --canary`. Скрипт является единственной точкой создания, найма, развёртывания AGENTS.md, рабочих каталогов, Codex subagents и записи в watchdog. Он ведёт journal и компенсирует неудачное создание компании.

### 3.1.1. Источник и состояние на iMac

Рабочий источник — приватный `github.com/ant013/full-audit.git`, checkout `/Users/Shared/Ios/full-audit`, ветка `main`. Bootstrap получает этот путь только через host-local `paths.yaml`.

После принятого отчёта только `FullAuditReportPublisher` может сделать fast-forward-safe commit и push изменённых `runs/` и `reports/` в этот remote. Он сначала проверяет чистоту вне этих каталогов, делает `git fetch origin`, останавливается при расхождении `origin/main`, затем коммитит только валидированные артефакты. `site/dist/` остаётся генерируемым и не коммитируется. Изменение критериев, скриптов или ролей не является частью аудиторского child issue и продолжает идти отдельной reviewable веткой.

### 3.1.2. Принудительная песочница

Расширить `bootstrap-project.sh` минимальным manifest-driven контрактом sandbox, не меняющим legacy-проекты по умолчанию:

- если манифест не объявляет sandbox, сохраняется текущее legacy-поведение;
- если `fullaudit` объявляет constrained mode, в `adapterConfig` передаются `dangerouslyBypassApprovalsAndSandbox: false`, `writableRoots` и `sourceRootsReadOnly`, вычисленные из host-local `paths.yaml`;
- bootstrap создаёт для каждого агента отдельный scratch; каждый агент получает только свой scratch и workspace;
- `FullAuditCTO` дополнительно получает `runs/`; `FullAuditReportPublisher` — `runs/`, `reports/`, `site/dist/`; аудиторы, verifier и QA не получают общих write roots;
- все `workspace/repos/` передаются как read-only source root. Никакой manifest, bundle или issue не может расширить эти корни абсолютным путём из Git.

Скрипт валидирует, что вычисленные roots существуют, расположены ниже checkout fullAudit и не пересекают `.env`, `ops/.env`, `.git` либо весь home-directory. Тесты проверяют точный payload `agent-hires` и сохранение legacy-пути для существующих проектов.

### 3.2. Состав команды

| Агент | Роль и граница |
|---|---|
| `FullAuditCEO` | Внешний roadmap walker: определяет `resume/start/done`, держит один родительский issue и создаёт максимум один дочерний issue. Не пишет отчёты и не проводит аудит. |
| `FullAuditCTO` | Внутренний координатор одного кита: фиксирует SHA, создаёт `plan.json`, назначает домены, собирает результаты, запускает верификацию, но не исследует домены вместо аудиторов. |
| `FullAuditSwiftAuditor` | Назначенные Swift/iOS-домены; только чтение клонов, строгий JSON домена. |
| `FullAuditKotlinAuditor` | Назначенные Kotlin/Android-домены; только чтение клонов, строгий JSON домена. |
| `FullAuditProtocolAuditor` | Криптография, подписи, консенсус, транзакции, parity; только чтение и строгий JSON домена. |
| `FullAuditEvidenceReviewer` | Независимая трёхлинзовая попытка опровергнуть Medium/High/Critical; не изменяет результаты координатора. |
| `FullAuditReportPublisher` | Собирает русский отчёт только из сохранённых доменных JSON, запускает валидатор и `bin/publish.sh`; не меняет исходники китов. |
| `FullAuditQAEngineer` | Независимо проверяет шапку/аттестацию, `runs/state.json`, локальную сборку сайта и защищённый HTTP 200. Не публикует и не исправляет отчёт. |

`FullAuditCEO → FullAuditCTO →` остальные шесть ролей. У каждого агента один concurrent run; роли разделены по issue и артефактам, чтобы два автора не редактировали один и тот же отчёт.

В проект копируются два неизменённых read-only Codex subagent-контракта из fullAudit:

- `fullaudit-domain-auditor` — один домен, один кит, строгий JSON и обязательная аттестация;
- `fullaudit-verifier` — одна находка, одна из линз `correctness/reachability/reproducibility`, строгий JSON-вердикт.

### 3.3. Рабочий поток

1. После успешного canary smoke создаётся один родительский issue «fullAudit: программа 32 библиотек», назначенный `FullAuditCEO`, и отправляется wake-comment.
2. CEO сверяет курсор на диске через `bin/next_kit.py`. При `done` публикует финальную сводку и останавливается; при `resume/start` создаёт один дочерний issue для соответствующего кита и блокирует родителя им.
3. CTO подготавливает только read-only clone, фиксирует commit один раз и сохраняет план в `runs/<slug>/plan.json`.
4. Доменные аудиторы возвращают JSON; CTO немедленно сохраняет `domain-<X>.json` и вызывает `record.py domain`. Клоны `workspace/repos/` не получают прав на запись.
5. Каждый Medium/High/Critical проходит все три независимые линзы верификации. Подтверждённой остаётся только находка, которую опровергло не более одной линзы; всё другое попадает в «Неподтверждённое».
6. Publisher создаёт отчёт по шаблону, запускает `validate_report.py`, `record.py finish` и `publish.sh`. Ошибка валидации возвращает issue Publisher, а не допускает публикацию.
7. QA проверяет точный опубликованный результат. После PASS CTO закрывает child, CEO снимает блокировку родителя и завершает свой run. Следующий запуск CEO берёт только следующий кит.

Bootstrap не создаёт периодическую routine: повторный запуск инициируется родительским issue или оператором. Это исключает параллельные аудиты и совпадает с принципом «один кит за запуск».

## 4. Объём изменений

Создаются только артефакты Paperclip:

- `paperclips/projects/fullaudit/paperclip-agent-assembly.yaml`;
- `paths.local-example.yaml`, `bindings.local-example.yaml`, `WORKFLOW.md`, roster и Codex overlay;
- восемь узких `roles-codex/*.md`;
- `codex-agents/fullaudit-domain-auditor.toml` и `fullaudit-verifier.toml`;
- `paperclips/scripts/bootstrap-project.sh` и его тесты — только для manifest-driven constrained sandbox payload, в обратной совместимости с legacy-проектами;
- tests, проверяющие манифест, точный roster, read-only ограничения, workflow и вызовы bootstrap/smoke.

Не входят в объём: изменения исходников 32 китов, их зависимостей, живой `UnstoppableAudit`, моделей Paperclip, Telegram-маршрутизации или публичного nginx. Telegram остаётся необязательным; основным каналом является отчётный сайт.

## 5. Матрица дельт и инвариантов

| Срез | Проверенный аналог | Сохраняемый инвариант | Нужная дельта | Отвергнутая дельта |
|---|---|---|---|---|
| Жизненный цикл компании | `projects/thorchain` + `bootstrap-project.sh` | manifest без host-local секретов/UUID; topological hire; journal; canary и smoke | ключ `fullaudit`, `FUL`, восемь аудит-ролевых агентов и host path checkout fullAudit | ручной API-найм или копирование UUID/путей другого проекта |
| Процесс и handoff | `projects/thorchain/WORKFLOW.md` | один активный child, явный comment→assign→verify handoff, независимый QA | child означает кит и завершается публикацией, а не product PR/merge | постоянная routine или параллельные киты |
| Аудиторские границы | `projects/uaudit` и read-only TOML | отдельные аудиторы, запрет секретов и записи в исходники | доменный JSON, доказательная планка, три линзы и артефакты `runs/` | 17 PR-ориентированных iOS/Android ролей или анализ только diff |
| Runtime sandbox | `bootstrap-project.sh` + `ops/imac-paperclip.md` | agent config определяет доступы, а не только текст роли | optional constrained manifest mode с узкими host-resolved roots | current global bypass или hardcoded абсолютные пути в Git |
| Приёмка | `smoke-test.sh` | API→agent→workspace→watchdog→runtime→handoff проверяется реальным control-plane | добавить проверку валидатора отчёта и авторизованного HTTP 200 сайта | считать созданную компанию работающей без реального handoff и публикационного smoke |

## 6. Приёмочные критерии

1. Manifest проходит `validate-manifest.sh fullaudit`, не содержит UUID, секретов и абсолютных путей.
2. Ровно восемь Codex агентов имеют `gpt-5.6-sol`, `xhigh`, managed instructions, корректный `reportsTo` и единственную ответственность.
3. Доменные и verifier subagents read-only, не читают credentials и возвращают только оговорённые JSON-контракты; live `agent-hires` config fullAudit содержит `dangerouslyBypassApprovalsAndSandbox: false`, узкие writable roots и `workspace/repos/` в read-only roots.
4. Bootstrap с config iMac создаёт/переиспользует только `fullAudit`, без изменения других компаний; `FUL` уникален.
5. Canary и полный smoke проходят: Board API, агенты, AGENTS.md workspaces, watchdog, профильные runtime-probes и e2e handoff.
6. Родительский issue создан только после smoke; запущен ровно один дочерний issue первого/возобновляемого кита.
7. На тестовом прогоне report validator принимает отчёт, state согласован, сайт после publish выдаёт авторизованный HTTP 200. Секреты не попадают в issue, отчёт или git.

## 7. План проверки

До live:

```bash
bash paperclips/scripts/validate-manifest.sh fullaudit
./paperclips/build.sh --project fullaudit --target codex
python3 paperclips/scripts/build_project_compat.py --project fullaudit --inventory update
python3 paperclips/scripts/validate_instructions.py --repo-root .
python3 -m pytest paperclips/tests/test_phase_f_thorchain_assembly.py paperclips/tests/test_phase_c_bootstrap_project.py paperclips/tests/test_phase_c_smoke_test.py <новый_тест_fullaudit> <новый_тест_sandbox>
git diff --check
```

На iMac после merge/release cut:

```bash
bash paperclips/scripts/bootstrap-project.sh fullaudit --config ~/.paperclip/projects/fullaudit/paths.yaml --canary
bash paperclips/scripts/smoke-test.sh fullaudit --cleanup-issues
```

После запуска родительского issue QA подтверждает `python3 bin/validate_report.py <slug>`, согласованность `runs/state.json`, `bash bin/publish.sh` и HTTP 200 с credentials только из host-local `.env`.

## 8. Подтверждённая предпосылка запуска

Приватный remote и iMac checkout созданы до реализации по прямому распоряжению оператора. HTTPS-remote на iMac использует уже настроенный GitHub credential helper; токены не попали в remote URL, Git или логи. Последующая реализация добавит путь checkout в host-local `paths.yaml`, а не в manifest.

## 9. Адверсариальная проверка дизайна

- **D-001, ACCEPT:** ThorChain — актуальный структурный аналог компании, но не процессный аналог аудита; его product-mainline/PR поведение исключено дельтой.
- **D-002, ACCEPT:** UAudit доказывает read-only специализацию, но его 17 агентов и PR-delta вход несовместимы; fullAudit ограничен восемью ролями и читает целые клоны.
- **D-003, ACCEPT:** Возможность «просто включить routine» отвергнута: она нарушает один-китовую последовательность и может создать конкурирующие записи в `runs/`.
- **D-004, ACCEPT:** Публикация остаётся отдельной ролью, QA независим; нельзя считать завершением факт создания markdown без validator, state и HTTP evidence.
- **D-005, ACCEPT (ревизия 2):** приватный source remote и чистый iMac checkout теперь существуют и совпадают по SHA; путь остаётся host-local.
- **D-006, ACCEPT:** текущий global sandbox bypass нельзя наследовать. Optional constrained mode ограничивает fullAudit без риска регрессии legacy-манифестов; payload и backward compatibility проверяются тестом.

## 10. Вне реализации до одобрения

До прямого одобрения этой спецификации запрещены создание компании, агентный найм, загрузка инструкций, создание routine/issue, запись в `~/.paperclip`, работа с watchdog и развёртывание на iMac.
