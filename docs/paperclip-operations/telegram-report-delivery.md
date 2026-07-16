# Доставка отчётов UAudit в Telegram

Этот runbook описывает операторский путь доставки UAudit после перехода на
`uaudit-delivery/v1`. Полную процедуру нельзя копировать в инструкции агентов.

## Текущие значения

| Поле | Значение |
|---|---|
| Company ID | `8f55e80b-0264-4ab6-9d56-8b2652f18005` |
| Telegram plugin ID | `60023916-4b6c-40f5-829f-bc8b98abc4ed` |
| Route | `UAudit` |
| Issue identifier | `UNS-*` |
| Android delivery owner | `UWAInfraEngineer` |
| iOS delivery owner | `UWIInfraEngineer` |
| Plugin SHA | `84c492d987ad0c16dcd224294b0747d60cd0d41f` |
| Helper path | `<team_workspace_root>/.uaudit-tools/uaudit_delivery_contract.py` |

Telegram chat/topic выбирается только через plugin `fileRoutes`. Не передавайте
`chatId`, bot token, URL или `filePath`.

## Контракт сообщения

`telegram-summary.txt` всегда на русском языке и содержит статус аудита, общее
число уникальных замечаний после дедупликации, четыре severity-счётчика и
вердикт. Ограничения методики, конфликты и области без findings в это число не
входят. Текст короче 900 UTF-8 bytes.

Пример:

```text
Аудит iOS PR #456 завершён
Найдено замечаний: 4
Критические: 0 · Блокирующие: 1 · Важные: 2 · Наблюдения: 1
Вердикт: блокирует принятие
```

Режим выбирается только из валидного `delivery-summary.json`:

- `complete` и ноль замечаний — `mode=message`; отправляется только `text`, MD
  не создаётся, а `audit.md` и `audit-final.md` должны отсутствовать;
- positive или любой `partial` — `mode=document`; тот же summary передаётся как
  caption вместе с `audit.md` (PR) либо `audit-final.md` (daily);
- blocked/malformed — ничего не отправляется и cursor не меняется.

Partial даже при нуле всегда получает MD и явно сообщает о неполном покрытии.

## Проверка pin, helper и worker

До production delivery проверьте локальный install proof:

```bash
EXPECTED=84c492d987ad0c16dcd224294b0747d60cd0d41f
PROOF="$HOME/.paperclip/plugin-proofs/telegram-loaded.json"
PENDING="$HOME/.paperclip/plugin-proofs/telegram-pending-reinstall.json"

test ! -e "$PENDING"

jq -e --arg expected "$EXPECTED" '
  .schema_version == "telegram-plugin-loaded-proof/v2" and
  .source_ref == $expected and
  .source_head == $expected and
  .status == "ready" and
  .registry_healthy == true and
  .runtime_attestation == {
    action: "send_to_telegram",
    code: "invalid_route_context",
    invalid_field: "issueIdentifier"
  }
' "$PROOF"

PLUGIN_ROOT=$(jq -r '.package_path' "$PROOF")
test "$(git -C "$PLUGIN_ROOT" rev-parse HEAD)" = "$EXPECTED"
test "$(shasum -a 256 "$PLUGIN_ROOT/dist/worker.js" | awk '{print $1}')" = \
  "$(jq -r '.worker_sha256' "$PROOF")"
```

Proof связывает полный Git SHA, digest собранного worker, immutable runtime
package path, stable plugin ID, registry `/health` и безотправочный вызов action,
который действительно проходит через worker и возвращает ожидаемую строгую
валидацию route context. Он не заменяет production Telegram canary.

`install-paperclip.sh` получает токен только из versioned auth-store entry для
нормализованного API URL и до подготовки/unload проверяет доступ к admin-only
plugin API. Нужен именно instance-admin Board credential. Целевая generation
собирается в новом каталоге; активный `packagePath` до unload не изменяется.
Перед unload installer снимает read-only rollback snapshot фактического
активного `packagePath`, фиксирует digest всего дерева и config digest,
публикует pending marker и удаляет прежний proof. Admin preflight использует
instance-admin-only `GET /api/instance/scheduler-heartbeats`.

Helper проверяет собственные bytes по соседнему manifest:

```bash
HELPER="<team_workspace_root>/.uaudit-tools/uaudit_delivery_contract.py"
MANIFEST="<team_workspace_root>/.uaudit-tools/uaudit_delivery_contract.manifest.json"
python3 "$HELPER" verify-install --manifest "$MANIFEST"
test ! -w "$HELPER"
```

Любое несовпадение SHA, writable helper, отсутствующий manifest, существующий
pending marker или неподтверждённый worker блокирует rollout. Helper чинится
повторным `bootstrap-project.sh uaudit`. Plugin installer намеренно не
перезаписывает pending: сначала выполните rollback ниже, проверьте его, явно
удалите/архивируйте pending marker и только затем повторите step 5. Не
ослабляйте проверки вручную. Helper installer отличает split-rename от tampering по read-only
transaction marker и безопасно завершает прерванную публикацию при повторе.

На чистой установке без plugin config installer сохраняет stable plugin ID в
host registry и `telegram-awaiting-attestation.json`, но не создаёт loaded
proof. Сначала настройте plugin, затем повторите step 5; успешная attestation
удалит awaiting marker.

## Штатная доставка и resume

Infra сначала запускает `verify-payload` для текущего run/handoff. Action
получает `issueIdentifier` (либо другой согласованный route context), `text` и,
только для document mode, `markdownContent` с `markdownFileName`.

Успешный ответ обязан содержать:

- `ok:true`;
- `routeSource:"file_route"`;
- `routeName:"UAudit"`;
- ожидаемый `mode:"message"` или `mode:"document"`;
- текущий `issueIdentifier` и непустой `messageId`.

Raw JSON-ответ сначала сохраняется в run directory. Затем Infra вызывает
`record-delivery`; helper проверяет route/mode/digests и атомарно создаёт
receipt. Только matching receipt разрешает последующие comment/status/cursor
шаги.

При повторном запуске:

1. Matching receipt запрещает повторную отправку; продолжайте reconciliation
   Telegram marker, daily cursor и workflow marker.
2. Conflicting receipt, receipt без валидного summary или marker без receipt
   блокируют run.
3. Если action мог успешно отправить сообщение, но процесс упал до записи raw
   response/receipt, автоматический retry может создать duplicate. Не заявляйте
   exactly-once; оператор сверяет Telegram и issue перед повтором.
4. Daily cursor меняется compare-and-set только после matching receipt. Для
   `partial` дополнительно требуется digest-bound approval разрешённого
   человека.

Cursor означает `last_successfully_audited_sha`. Не продвигайте его вручную
после failed, blocked или permission-denied delivery.

## Board access required

Если корректный payload получил `Board access required`, исправляйте live
`adapterConfig.env` Infra-агента:

- добавьте Board-scoped `PAPERCLIP_API_KEY` и `PAPERCLIP_API_URL`;
- сохраните `cwd`, `CODEX_HOME`, `PATH`, model, sandbox и extra args;
- повторите только заблокированную delivery issue.

Не обходите ошибку через `chatId`, Telegram token, прямой
`api.telegram.org`, URL, `filePath` или чтение operator `.env` агентом.

## Canary

Live Telegram smoke выполняется только после явного разрешения оператора:

1. Прогоните полный plugin test suite до pin/install.
2. Проверьте loaded proof и worker health.
3. Отправьте positive/partial document canary и подтвердите `UAudit`,
   `file_route`, `mode=document`, имя файла и `messageId`.
4. Отправьте отдельный complete-zero canary без Markdown-полей и подтвердите
   `UAudit`, `file_route`, `mode=message`, русский summary и отсутствие обоих
   report paths.
5. Создайте receipt и завершите resume/reconciliation path для обоих canary.

До успешного шага 4 complete-zero production path не включается.

## Rollback plugin

Installer до остановки старого worker создаёт собранную rollback generation и
пишет её путь в loaded proof. Остановите новые UAudit delivery, затем используйте
прямой API (Paperclip CLI flags не предполагаются):

```bash
PROOF="$HOME/.paperclip/plugin-proofs/telegram-loaded.json"
PENDING="$HOME/.paperclip/plugin-proofs/telegram-pending-reinstall.json"
if [ -f "$PENDING" ]; then
  ROLLBACK=$(jq -r '.rollback_manifest' "$PENDING")
else
  ROLLBACK=$(jq -r '.rollback_manifest' "$PROOF")
fi
PLUGIN_ID=$(jq -r '.plugin_id' "$ROLLBACK")
PACKAGE_PATH=$(jq -r '.package_path' "$ROLLBACK")
EXPECTED_WORKER=$(jq -r '.worker_sha256' "$ROLLBACK")
EXPECTED_TREE=$(jq -r '.package_tree_sha256' "$ROLLBACK")
EXPECTED_CONFIG=$(jq -r '.config_sha256' "$ROLLBACK")

test -f "$PACKAGE_PATH/dist/worker.js"
test "$(shasum -a 256 "$PACKAGE_PATH/dist/worker.js" | awk '{print $1}')" = \
  "$EXPECTED_WORKER"

ACTUAL_TREE=$(python3 - "$PACKAGE_PATH" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1]); digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
    rel = path.relative_to(root).as_posix().encode()
    if path.is_symlink():
        digest.update(b"L\0" + rel + b"\0" + path.readlink().as_posix().encode() + b"\0")
    elif path.is_file():
        data = path.read_bytes()
        digest.update(b"F\0" + rel + b"\0" + str(len(data)).encode() + b"\0" + data)
    elif path.is_dir():
        digest.update(b"D\0" + rel + b"\0")
print(digest.hexdigest())
PY
)
test "$ACTUAL_TREE" = "$EXPECTED_TREE"

curl -fsS -X DELETE \
  "${PAPERCLIP_API_URL%/}/api/plugins/$PLUGIN_ID" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"

jq -n --arg packageName "$PACKAGE_PATH" \
  '{packageName:$packageName,isLocalPath:true}' |
curl -fsS -X POST \
  "${PAPERCLIP_API_URL%/}/api/plugins/install" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @-

curl -fsS \
  "${PAPERCLIP_API_URL%/}/api/plugins/$PLUGIN_ID/health" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" |
jq -e '.status == "ready" and .healthy == true'

jq -n '{params:{companyId:"uaudit-install-attestation",agentId:"operator"}}' |
curl -fsS -X POST \
  "${PAPERCLIP_API_URL%/}/api/plugins/$PLUGIN_ID/actions/send_to_telegram" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- |
jq -e '.data.data.ok == false and .data.data.code == "missing_content"'

ACTUAL_CONFIG=$(curl -fsS \
  "${PAPERCLIP_API_URL%/}/api/plugins/$PLUGIN_ID/config" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" | jq -cS -j . |
  python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')
test "$ACTUAL_CONFIG" = "$EXPECTED_CONFIG"
```

Soft uninstall сохраняет stable plugin ID, config и plugin-scoped data. Если
installer упал между unload/install, `telegram-pending-reinstall.json` указывает
на подготовленную generation, а usable loaded proof отсутствует. Автоматический
rollback сверяет ID, фактический package path, config, registry health и вызов
worker. Даже после успешного rollback pending marker сохраняет delivery
остановленной. После всех проверок выше архивируйте marker, удалите его из
`plugin-proofs` и повторите step 5; новый loaded proof появится только после
успешного rollout целевого SHA.

## Rollback helper

Остановите активные UAudit runs. Из доверенного предыдущего Gimle commit
восстановите helper во временный файл, вычислите SHA, опубликуйте helper первым,
а adjacent manifest последним, оба с mode `0444`. Затем обязательно выполните
`verify-install`. Проще и безопаснее запустить `bootstrap-project.sh uaudit` из
отдельного worktree предыдущего Gimle commit: bootstrap принимает только
целостную текущую generation и атомарно заменяет её на bytes этого checkout.

После любого rollback повторите document canary. Complete-zero можно вернуть в
production только после нового route-aware text-only canary.
