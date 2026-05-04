# Runbook: Multi-repo SPM ingest (uw-ios bundle) — GIM-182

## Обзор

`uw-ios` — виртуальный bundle, объединяющий UW iOS app и 40 first-party HorizontalSystems Swift Kits.
После успешного ingest `palace.code.find_references(qualified_name="EvmKit.Address", project="uw-ios")`
разрешает usages по всем 41 репозиториям в одном вызове.

Smoke gate: `uw-ios-app` slug обязателен (`ok=True`) + `members_ok >= 40`.

---

## 1. One-time setup (iMac)

### 1.1 Disk budget preflight

```bash
ssh imac-ssh.ant013.work bash -c '
  free_gb=$(df -g /Users/Shared/Ios | awk "NR==2 {print \$4}")
  if [ "$free_gb" -lt 15 ]; then
    echo "ERROR: need >=15GB free; have ${free_gb}GB" >&2; exit 1
  fi
  echo "OK: ${free_gb}GB free"
'
```

### 1.2 Clone все 41 репозитория

```bash
ssh imac-ssh.ant013.work bash -c '
  mkdir -p /Users/Shared/Ios/HorizontalSystems
  python3 ~/Gimle-Palace/services/palace-mcp/scripts/_clone_kits.py \
    --manifest ~/Gimle-Palace/services/palace-mcp/scripts/uw-ios-bundle-manifest.json \
    --base /Users/Shared/Ios/HorizontalSystems
  chmod -R go+rX /Users/Shared/Ios/HorizontalSystems
'
```

### 1.3 Перезапуск palace-mcp с HS mount

```bash
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace && docker compose --profile review up -d --force-recreate palace-mcp'
```

Убедиться что `/repos-hs` виден в контейнере:

```bash
ssh imac-ssh.ant013.work \
  'docker compose --profile review exec palace-mcp ls /repos-hs | head -5'
```

---

## 2. Регистрация bundle через MCP

```bash
ssh imac-ssh.ant013.work \
  'bash ~/Gimle-Palace/services/palace-mcp/scripts/register-uw-ios-bundle.sh'
```

Скрипт идемпотентен (безопасно перезапускать).
Проверить результат:

```python
palace.memory.bundle_members(bundle="uw-ios")
# → 41 ProjectRef записей
```

---

## 3. Генерация SCIP индексов (dev Mac)

```bash
# На dev Mac (требуется palace-swift-scip-emit + SSH до iMac):
cd ~/HorizontalSystems
bash ~/Gimle-Palace/services/palace-mcp/scripts/regen-uw-ios-scip.sh
```

Скрипт: mtime-guard (пропускает актуальные), sha256 verification, rsync до iMac.
Log: `~/Library/Logs/palace-uw-ios-regen.log` (ротация 10 MB × 3 файла).

После regen проверить sha256:

```bash
ssh imac-ssh.ant013.work \
  'ls /Users/Shared/Ios/HorizontalSystems/EvmKit.Swift/scip/'
# ожидается: index.scip  index.scip.sha256
```

---

## 4. Запуск ingest

```python
# MCP (async — возвращает run_id немедленно):
palace.ingest.run_extractor(name="symbol_index_swift", bundle="uw-ios")
# → {"run_id": "rb-...", "state": "running", "members_total": 41}

# Polling:
palace.ingest.bundle_status(run_id="rb-...")
# → {"state": "succeeded"/"failed", "members_ok": ..., "members_failed": ...}
```

---

## 5. Smoke gate

```bash
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace && uv run python services/palace-mcp/scripts/smoke_uw_ios_bundle.py' \
  | tee /tmp/uw-ios-smoke-$(date +%s).log
echo "Exit code: $?"
```

**GREEN criteria:**
- `ingest_summary.members_ok >= 40`
- `uw-ios-app` не в failed runs
- `occurrences_count > 0` для `EvmKit.Address`
- `bundle_health.members_total == 41`
- `uw-ios-app` не в `query_failed_slugs`, `ingest_failed_slugs`, `never_ingested_slugs`

---

## 6. Устранение неисправностей

### Member ingest failed

Проверить per-member ошибку:

```python
status = palace.ingest.bundle_status(run_id="rb-...")
failed = [r for r in status["runs"] if not r["ok"]]
# r["error_kind"]: file_not_found | extractor_error | tantivy_disk_full | neo4j_unavailable | unknown
# r["error"]: message
```

Для `file_not_found`: убедиться что `/repos-hs/<relative_path>/scip/index.scip` существует в контейнере.

```bash
ssh imac-ssh.ant013.work \
  'docker compose --profile review exec palace-mcp ls /repos-hs/EvmKit.Swift/scip/'
```

### Path / mount errors

Убедиться что `register_project` был вызван с правильным `parent_mount="hs"` и `relative_path`:

```python
palace.memory.bundle_members(bundle="uw-ios")
# каждый member должен иметь parent_mount="hs"
```

### Bundle membership drift

Если новый Kit добавился в UW-iOS `Package.resolved` но не в manifest:

```bash
python3 services/palace-mcp/scripts/diff-manifest-vs-package-resolved.py \
  --manifest services/palace-mcp/scripts/uw-ios-bundle-manifest.json \
  --package-resolved /path/to/unstoppable-wallet-ios/Package.resolved
```

Добавить в `uw-ios-bundle-manifest.json` → перезапустить `register-uw-ios-bundle.sh`.

---

## 7. Cleanup

Удалить bundle (не удаляет member :Project ноды, только :Bundle + :CONTAINS):

```python
palace.memory.delete_bundle(name="uw-ios", cascade=True)
# Затем перерегистрировать: bash register-uw-ios-bundle.sh
```

---

## 8. Ключевые инварианты

1. `:Bundle.group_id = "bundle/uw-ios"` — всегда.
2. `register_parent_mount` — не существует как v1 MCP tool; `parent_mount` — параметр `register_project`.
3. Bundle ingest async: `run_extractor(bundle=...)` возвращает `run_id` за < 100 ms; тяжёлый ingest в background.
4. `failed_slugs` делится на три: `query_failed_slugs` (query-time), `ingest_failed_slugs` (last_run failed), `never_ingested_slugs` (no run).
5. Smoke gate: `uw-ios-app` ok + `members_ok >= 40` обязательны для GREEN.
