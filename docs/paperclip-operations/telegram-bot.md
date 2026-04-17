# Telegram Bot — Operational Runbook

Bot `@gimle_palace_bot` bridges Paperclip ↔ GimleOps Telegram supergroup (`-1003521772993`).
Plugin: `paperclip-plugin-telegram v0.3.0`.

---

## 1. Install

```bash
paperclipai plugin install paperclip-plugin-telegram
paperclipai plugin list   # verify state = enabled
```

## 2. Provision secret

Before configuring, store the bot token as a Paperclip Secret (never in env files or git):

```bash
paperclipai secret create --name telegram-bot-token
# paste token when prompted — receives a Secret UUID
```

## 3. Configure

Use the Secret UUID (not the raw token) for `botToken`:

```bash
paperclipai plugin config set paperclip-plugin-telegram \
  botToken=secret:<SECRET_UUID> \
  defaultChatId=-1003521772993 \
  enableInbound=true \
  enableCommands=true
```

Minimal event filter (expand later via the same command):

```bash
paperclipai plugin config set paperclip-plugin-telegram \
  eventFilter=issue.closed,agent.error,approval.requested
```

## 4. Activate — required disable+enable cycle

> **Gotcha:** After the first config set, the worker stays in a half-initialised state.
> Telegram polling never starts and bot commands are not registered.
> Fix: force a restart manually.

```bash
paperclipai plugin disable paperclip-plugin-telegram
paperclipai plugin enable  paperclip-plugin-telegram
paperclipai plugin inspect paperclip-plugin-telegram  # confirm state = running
```

Do this after any config change that touches `botToken` or `defaultChatId`.

## 5. Verify

- Send `/status` in the GimleOps supergroup — bot replies with live Paperclip data.
- Send `/help` to confirm all commands are registered.
- Close a minor issue in Paperclip — notification should arrive in the group.

## 6. Token rotation

1. In BotFather: `/revoke` → receive new token.
2. Create a new Paperclip Secret with the new token.
3. Update the config with the new Secret UUID (step 3 above).
4. Run the disable+enable cycle (step 4 above).
5. Delete the old Paperclip Secret.

## 7. Uninstall

```bash
paperclipai plugin disable paperclip-plugin-telegram
paperclipai plugin uninstall paperclip-plugin-telegram
```

Config and secrets are not deleted automatically — remove the Paperclip Secret manually if the bot token should be revoked.

---

## Reference

| Item | Value |
|---|---|
| Bot username | `@gimle_palace_bot` |
| Telegram group chat ID | `-1003521772993` |
| Plugin key | `paperclip-plugin-telegram` |
| Plugin version | `0.3.0` |
| Inbound enabled | yes (`enableInbound=true`) |
| Bot commands enabled | yes (`enableCommands=true`) |

Chat IDs are not sensitive and safe to document here.
Bot tokens and Secret UUIDs are sensitive — never commit them to git.
