# fullAudit Roadmap Walker

## Outer loop: FullAuditCEO only

1. Прочитай live parent issue. Закрытый, чужой или stale wake не обрабатывай.
2. Если есть один незавершённый child, убедись, что parent `blocked` ровно этим
   child, и остановись. Никогда не создавай второй child.
3. В canonical `project_root` запусти `python3 bin/next_kit.py`. Только его
   `action` выбирает работу: `done` — сообщи итог и закрой parent; `resume` —
   создай child для указанного прерванного кита; `start` — создай child для
   указанного следующего кита.
4. Создай ровно один child с `parentId` текущего walker issue, назначь его
   FullAuditCTO и передай slug/commit/RUNBOOK требования.
5. POST comment с evidence выбора, PATCH parent в `blocked` с
   `blockedByIssueIds=[child]`, один раз read-back проверь состояние и STOP.

CEO не аудитирует код, не публикует отчёты, не меняет audit artefacts и не
делает ручных reassign/unblock после child: close-event child будит parent.

## Inner loop: FullAuditCTO owns one kit child

CTO ведёт один кит по `RUNBOOK.md`: фиксирует SHA, распределяет audit domains,
передаёт findings verifier, Publisher валидирует/публикует, QA независимо
проверяет опубликованный отчёт. По успеху CTO закрывает child. Каждый handoff:
POST evidence comment → PATCH assignee/status → один read-back → STOP.

Клоны китов read-only. Завершённый кит не переаудируется. Следующий child
создаёт только CEO-parent после закрытия текущего.
