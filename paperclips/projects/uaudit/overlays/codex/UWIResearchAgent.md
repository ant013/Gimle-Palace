## Daily Version-Branch Research Stage (iOS)

When assigned a UAudit daily version-branch issue with
`mode=daily_research`, read `$RUN/profile.json`, prior stage reports, and only
the external references needed to resolve open library, protocol, or platform
questions. Do not redo code/security/crypto review.

Write `$RUN/research-context.md` with cited context, impact on open findings,
and limitations. Then write `$RUN/research.done`, comment
`research-context.md ready for UNS-<N> iOS daily audit`, PATCH assignee to
`{{bindings.agents.UWIQAEngineer}}` with `mode=daily_qa_verify`, and stop.
