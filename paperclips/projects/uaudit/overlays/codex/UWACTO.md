
## UAudit PR Audit Routing (Android)

When an issue contains an Android PR URL matching:

```text
https://github.com/horizontalsystems/unstoppable-wallet-android/pull/<N>
```

do not run the old CTO-led multi-agent audit cycle. Route the issue to
`UWAKotlinAuditor`, which is the Android PR-audit coordinator for this project.

Required action:

1. Comment:
   `Routing Android PR audit to UWAKotlinAuditor coordinator.`
2. PATCH `assigneeAgentId` to
   `18f0ee3e-0fd9-40e7-a3b4-99a4ad3ab400`.
3. End your run.

If the issue contains an iOS PR URL, route to `UWICTO` instead. If the PR URL is
malformed or from another repository, comment a short blocker and keep the issue
assigned to yourself.
