## Daily Version-Branch QA Verification Stage (iOS)

When assigned a UAudit daily version-branch issue with `mode=daily_qa_verify`,
read `$RUN/profile.json`, prior stage reports, and available project tests.
Verify reproducibility or test coverage for high-risk findings when feasible;
record commands that cannot be run and why.

Write `$RUN/qa-verify.md` with verification results, residual risks, and exact
commands/evidence. Then write `$RUN/qa.done`, comment
`qa-verify.md ready for UNS-<N> iOS daily audit`, PATCH assignee to
`{{bindings.agents.UWICTO}}` with `mode=daily_aggregate`, and stop. Do not send
Telegram or update cursors.
