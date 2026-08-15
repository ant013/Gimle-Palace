# fullAudit: доступ к локальному Paperclip API через bypass sandbox

## Контекст и решение

На iMac Paperclip слушает только `http://127.0.0.1:3100`. В strict Codex
sandbox этот адрес относится к изолированному loopback агента, а не к iMac:
контрольные задачи FUL-43 подтвердили `connection refused`. Оператор явно
разрешил включить `--dangerously-bypass-approvals-and-sandbox` для fullAudit,
как у работающих host-local агентов.

Решение: сохранить `constrained`-контракт fullAudit для cwd, разрешённых
write roots, read-only source roots и host-resolved loopback URL, но добавить
явный manifest opt-in `sandbox.bypass_approvals_and_sandbox: true`. Bootstrap
передаст его только как
`adapterConfig.dangerouslyBypassApprovalsAndSandbox`.

## Предпосылки

- Paperclip API и все восемь агентов остаются на iMac; публичный API и nginx
  не меняются.
- Bypass даёт runtime-процессу агента host-level доступ, поэтому это намеренно
  снимает именно sandbox-изоляцию; пути записи по manifest остаются прежними.
- `PAPERCLIP_API_URL` остаётся host-local loopback; новый bridge, proxy,
  токены или секреты не вводятся.

## Scope

Входит:

- типизированный boolean opt-in в `paperclip-agent-assembly.yaml` fullAudit;
- bootstrap-разрешение этого boolean только для `constrained` manifest;
- узкие проверки manifest и bootstrap-контракта;
- регенерация resolved assembly при изменении hash manifest;
- canary bootstrap и полный disposable smoke на iMac после merge.

Не входит:

- смена модели, MCP-набора, ролей, writable/read-only roots или URL API;
- изменение других компаний, Paperclip host binding, firewall, nginx,
  секретов или исходников проверяемых китов;
- запуск нового аудита до успешного smoke.

## Аffected areas

- `paperclips/projects/fullaudit/paperclip-agent-assembly.yaml`
- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/tests/test_fullaudit_assembly.py`
- `paperclips/dist/fullaudit.resolved-assembly.json` (generated)

## Analog family and delta matrix

| Slice | Analog family | Invariant to preserve | Required delta | Rejected alternative | Failure mode / guard | Verification |
|---|---|---|---|---|---|---|
| S-001 host control-plane connectivity | Primary: constrained branch in `bootstrap-project.sh:514-568`; support: fullAudit manifest and its assembly test; counterexample: generic legacy default | constrained cwd must be a trusted Git worktree; writable/read-only roots and loopback URL validation remain manifest-resolved | read `sandbox.bypass_approvals_and_sandbox`, default false, validate it is boolean, and use it for the adapter flag | switch fullAudit to `legacy`, which would remove the constrained-root contract | a malformed non-boolean manifest must fail bootstrap; absent key remains false for compatible constrained projects | targeted pytest, shell syntax, manifest validation, project build; iMac canary + runtime smoke |

Coverage: contract (manifest), implementation/lifecycle/error (bootstrap),
composition/consumer (manifest-to-agent payload), test (assembly test), and a
rejected counterexample are all current-tree verified. `codebase-memory` and
Serena were unavailable in this session, so this family uses targeted `rg` and
current-tree reads; durable evidence is `audit/runs/fullaudit-enable-bypass-20260805/`.

## Acceptance criteria

1. fullAudit declares an explicit, readable bypass opt-in; no host paths or
   secrets are committed.
2. Bootstrap accepts only `true` or `false`, defaults to `false` if absent,
   and places the resolved value in
   `dangerouslyBypassApprovalsAndSandbox` without altering constrained root
   handling or `PAPERCLIP_API_URL` validation.
3. Existing generic legacy behavior remains unchanged.
4. The targeted test proves fullAudit's opt-in and the bootstrap resolution
   contract; manifest validation and project build pass.
5. After deployment, all eight fullAudit agent configs show bypass `true` and
   a single full disposable smoke succeeds before any roadmap issue is made.

## Test plan

Before code, extend `test_fullaudit_assembly.py` to assert the explicit
manifest opt-in and the bootstrap's boolean/default resolution markers. After
code run:

```bash
/Users/ant013/anaconda3/bin/python3 -m pytest \
  paperclips/tests/test_fullaudit_assembly.py \
  paperclips/tests/test_phase_c_smoke_test.py -v
bash -n paperclips/scripts/bootstrap-project.sh
python3 paperclips/scripts/build_project_compat.py --project fullaudit --target codex --inventory skip
bash paperclips/scripts/validate-manifest.sh fullaudit
git diff --check
```

Post-merge, bootstrap a clean iMac clone in canary mode, inspect all eight
agent configs through the authenticated API, then run exactly one disposable
`smoke-test.sh fullaudit --cleanup-issues`.

## Adversarial review

- **Security regression:** accepted intentionally by the operator; bounded to
  fullAudit via a manifest field, while all filesystem roots remain constrained.
- **Over-broad solution:** rejected legacy mode would discard root protections.
- **Bad manifest value:** bootstrap must reject values other than `true`/`false`.
- **Compatibility:** absent key defaults false, preserving every existing
  constrained manifest.
- **Operational proof:** a config-only test is insufficient; canary and runtime
  smoke are mandatory before launching the CEO roadmap.

Decision `D-001`: ACCEPT. The one-field opt-in is the smallest coherent change
that restores the necessary host-local control-plane connectivity while
preserving the fullAudit filesystem contract.

## Open questions

None for this bounded change. The residual risk is the operator-approved loss
of Codex sandbox isolation for fullAudit runtime processes.
