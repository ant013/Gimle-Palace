
## UAudit PR Audit Routing (iOS)

When an issue contains an iOS PR URL matching:

```text
https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/<N>
```

do not run the old CTO-led multi-agent audit cycle. Route the issue to
`UWISwiftAuditor`, which is the iOS PR-audit coordinator for this project.

Required action:

1. Comment:
   `Routing iOS PR audit to UWISwiftAuditor coordinator.`
2. PATCH `assigneeAgentId` to
   `a6e2aec6-08d9-43ab-8496-d24ce99ac0de`.
3. End your run.

If the issue contains an Android PR URL, route to `UWACTO` instead. If the PR
URL is malformed or from another repository, comment a short blocker and keep
the issue assigned to yourself.
