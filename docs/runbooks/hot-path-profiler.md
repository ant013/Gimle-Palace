# Hot-Path Profiler

## Назначение

`hot_path_profiler` читает профили выполнения из `/repos/<slug>/profiles/`,
сводит горячие функции по CPU/wall-time и связывает их с существующими
`:Function` узлами.

## Track A / Track B

- **Track A** — merge-gate fixture. Коммитим нормализованный JSON,
  полученный из `xctrace export`, в
  `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/`.
- **Track B** — optional live capture на dev Mac. Можно использовать для
  sanity-check после merge, но отсутствие Track B не блокирует PR.

## Как подготовить Instruments fixture

1. Запишите Time Profiler trace на Mac.
2. Экспортируйте таблицу:

```bash
xctrace export \
  --input /path/to/trace.trace \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="time-profile"]' \
  --output /tmp/time-profile.xml
```

3. Нормализуйте экспорт в JSON с полями:
   - `trace_id`
   - `threshold_cpu_share`
   - `summary.total_cpu_samples`
   - `summary.total_wall_ms`
   - `samples[].symbol_name`
   - `samples[].cpu_samples`
   - `samples[].wall_ms`
   - `samples[].thread_name`
4. Сохраните fixture рядом с metadata-файлом. Рекомендуемый размер каждого
   файла — меньше 1 MB.

## Как подготовить Perfetto fixture

1. Соберите `.pftrace` вне extractor’а.
2. Положите файл в `/repos/<slug>/profiles/`.
3. Убедитесь, что в `services/palace-mcp/pyproject.toml` доступна зависимость
   `perfetto`, а импорт проходит:

```bash
cd services/palace-mcp
uv run python -c "from perfetto.trace_processor import TraceProcessor"
```

## Запуск extractor’а

```text
palace.ingest.run_extractor(name="hot_path_profiler", project="<slug>")
```

После успешного запуска проверьте:

```cypher
MATCH (s:HotPathSample {project_id: "project/<slug>"})
RETURN s.trace_id, s.qualified_name, s.cpu_samples
ORDER BY s.cpu_samples DESC
```

## Troubleshooting

- Если extractor пишет `repo_not_mounted`, проверьте bind-mount проекта в
  `docker-compose.yml`.
- Если `profiles/` отсутствует, создайте каталог в корне смонтированного repo.
- Если растет `:HotPathSampleUnresolved`, проверьте совпадение trace symbol
  names с `qualified_name`/`display_name` на `:Function`.
- Если Perfetto parser падает на импорте, выполните `uv sync` в
  `services/palace-mcp/` и повторите import validation.
