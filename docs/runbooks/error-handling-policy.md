# Runbook: error_handling_policy

## Назначение

`error_handling_policy` проверяет Swift-код на антипаттерны обработки ошибок,
записывает `:ErrorFinding` и параллельно индексирует smoke-surface
`{:CatchSite}` для `catch` и `try?`.

## Что проверяется

Активные semgrep rules:

1. `empty_catch_block` — пустой `catch` или `catch`, который сразу делает `return` / `break` / `continue`.
2. `empty_catch_in_crypto_path` — такой же паттерн в crypto/sign/key/wallet/balance путях.
3. `try_optional_swallow` — `try?`, скрывающий исходную ошибку.
4. `try_optional_in_crypto_path` — `try?` в crypto-critical путях.
5. `catch_only_logs` — `catch`, который только логирует или печатает ошибку.
6. `generic_catch_all` — общий `catch { ... }` без typed binding.
7. `error_as_string` — строковый error payload вместо typed `Error`.
8. `nil_coalesce_swallows_error` — `try? ... ?? fallback`, скрывающий ошибку дефолтом.

## Подавление

Если swallow является осознанным, можно понизить finding до
`informational`, добавив комментарий на той же или предыдущей строке:

- `// ehp:ignore`
- `// MARK: deliberate`

Подавление не убирает `:CatchSite`; оно только снижает severity finding.

## Как запустить

Из `services/palace-mcp`:

```bash
uv run pytest tests/extractors/unit/test_error_handling_policy.py -v
uv run pytest tests/extractors/integration/test_error_handling_policy_integration.py -m integration -v
uv run ruff check src/palace_mcp/extractors/error_handling_policy tests/extractors/unit/test_error_handling_policy.py tests/extractors/integration/test_error_handling_policy_integration.py
uv run mypy src/palace_mcp/extractors/error_handling_policy
```

Для live smoke через MCP:

```python
palace.ingest.run_extractor(name="error_handling_policy", project="tronkit-swift")
```

## Что считать успешным smoke

- `:CatchSite` count > 0
- `:ErrorFinding` count > 0 или явный clean-result с указанным числом
  просмотренных файлов
- audit report рендерит секцию `error_handling_policy`

## Troubleshooting

- `semgrep rules directory not found` — проверьте, что пакет
  `src/palace_mcp/extractors/error_handling_policy/rules/` присутствует в ветке.
- `semgrep timed out` — увеличьте timeout через
  `palace_error_handling_semgrep_timeout_s` или повторите запуск на меньшем репозитории.
- Пустой report при непустом графе — проверьте, что query в `audit_contract()`
  получает `project_id = "project/<slug>"`.
