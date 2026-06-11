## Daily Version-Branch Crypto Audit Stage (iOS)

When assigned a UAudit daily version-branch issue with
`mode=daily_crypto_audit`, read `$RUN/profile.json`, `$RUN/diff.patch`,
`$RUN/code.md`, `$RUN/security.md`, and the iOS repo. Audit wallet, chain,
signing, transaction, key-management, address, fee, and balance semantics in
FROM..TO.

Write `$RUN/crypto.md` with crypto/blockchain findings, no-finding areas,
limitations, and exact evidence. Then write `$RUN/crypto.done`, comment
`crypto.md ready for UNS-<N> iOS daily audit`, PATCH assignee to
`{{bindings.agents.UWIInfraEngineer}}` with `mode=daily_infra_audit`, and stop.
Do not send Telegram, update cursors, or invoke `uaudit-*` Codex subagents.
