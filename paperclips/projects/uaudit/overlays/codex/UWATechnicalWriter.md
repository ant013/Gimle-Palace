## Daily bilingual audit translation

For `mode=daily_audit_translation`, this agent runs locally on the iMac. Read `$RUN/translation-input.json` and the exact `$RUN/audit-final.ru.md` bytes. Write a complete English translation to `$RUN/audit-final.en.md`; preserve every SHA, path, identifier, count, severity, range and technical fact exactly, translating only prose. End the file with one newline.

Then atomically write `$RUN/translation-result.json` with exactly `schema_version,run_binding_sha256,source_sha256,target_file,target_sha256`, using values from the input plus the SHA-256 of the English file. Do not send Telegram, mutate a cursor or lock, alter the Russian report, or create a delivery summary. Assign `{{bindings.agents.UWACTO}}` with `mode=daily_finalize_translation`.
