## Daily Version-Branch Security Audit Stage (Android)

When assigned a UAudit daily version-branch issue with
`mode=daily_security_audit`, read `$RUN/profile.json`, `$RUN/diff.patch`,
`$RUN/code.md`, and the Android repo. Audit auth, storage, networking, signing,
permission, privacy, dependency, and abuse-path changes in FROM..TO.

Write `$RUN/security.md` with security findings, no-finding areas, limitations,
and exact evidence. Then write `$RUN/security.done`, comment
`security.md ready for UNS-<N> Android daily audit`, PATCH assignee to
`{{bindings.agents.UWACryptoAuditor}}` with `mode=daily_crypto_audit`, and stop.
Do not send Telegram, update cursors, or invoke `uaudit-*` Codex subagents.
