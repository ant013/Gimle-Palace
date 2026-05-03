# Phase Handoff Lesson

This lesson backs the short handoff profile. It is background context, not the
only copy of the operational rule.

GIM-48 showed why phase ownership must be explicit: after CodeReviewer approved
Phase 3.1, the issue was moved to `todo` instead of assigned to QAEngineer.
CTO later saw the issue as ready, closed it, and code that had not passed live
QA smoke reached the iMac path. The failure mode was not a missing checklist; it
was an ownerless handoff.

The mandatory runtime rule stays inline in generated bundles:

- push before handoff;
- assign the next agent;
- @mention the next agent;
- include branch, commit SHA, evidence, and next action;
- do not use `status=todo` between phases;
- do not close without required downstream evidence.

Keep this lesson available for reviewers and maintainers when adjusting the
handoff profile, but do not replace the inline rule with only this reference
until runbook runtime access is proven.
