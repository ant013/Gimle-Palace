# fullAudit: smoke Git-probe по существующим profile fragments

## Решение

Не менять fullAudit role sources, profile mappings или shared fragments.
Thorchain и fullAudit собирают один и тот же composed bundle: universal слой,
затем profile fragments, затем короткая project-role задача и project overlay.
Profile — единственный источник Git-возможностей; workflow role отвечает только
за оркестрационные фазы. Existing fragments уже задают границы:

- `writer` — документация и handoff, без Git/worktree;
- `qa` наследует `implementer`, поэтому может commit/push;
- `cto` наследует reviewer, включает merge authority, release-cut и phase
  orchestration;
- `outer_walker` и `inner_orchestrator` остаются workflow-идентичностями
  существующего fullAudit manifest.

Исправить только smoke Git-probe:

1. определять Git policy по manifest `profile`, не переопределять её через
   `outer_walker` / `inner_orchestrator`;
2. вопрос намеренно требует две секции `Can` и `Cannot`, но текущая проверка
   ищет запрещённые токены во всём ответе. Из-за этого корректный writer
   ответ `Cannot: commit` ложно считается разрешением commit. Проверка должна
   искать required операции в полном ответе, а forbidden операции — только в
   части до маркера `Cannot:`.

## Scope

Входит:

- `paperclips/scripts/lib/_smoke_probes.sh`: выбор policy строго по profile и
  выделение разрешённой секции ответа Git-probe перед проверкой `must_not`;
- `paperclips/tests/test_phase_c_smoke_test.py`: структурный regression-тест
  нового разделения;
- при необходимости generated artifacts не меняются, поскольку assembly и
  fragments не меняются.

Не входит:

- любые новые Git-правила, локальные prompt overrides или изменения
  `roles-codex/*.md`;
- изменения profile fragments, manifest, bypass, MCP, ролей, root paths,
  Paperclip API или клонов китов.

## Analog family and delta

| Slice | Primary analog | Supporting evidence | Preserved invariant | Delta | Rejected alternative | Verification |
|---|---|---|---|---|---|---|
| Git capability smoke | `_check_markers` / `probe_agent_for_profile` | Thorchain composed bundles; `profiles/writer.yaml`, `profiles/qa.yaml`, `profiles/cto.yaml` | profile fragments remain the sole policy source; workflow role remains phase-only | select expected Git policy by profile and pass only the `Can` section to forbidden-operation checks | weaken restrictions, add local role prose, or use workflow role for Git policy | focused pytest, `bash -n`, then iMac full smoke |

## Acceptance criteria

1. A writer reply listing `commit`, `push`, or `merge` under `Cannot:` passes
   the writer forbidden-capability check.
2. The same operation under `Can:` fails that check.
3. Required operations remain checked against the complete reply.
4. No fullAudit role, manifest, fragment or sandbox configuration changes; the
   smoke code derives Git expectations solely from existing profile fragments.
5. Targeted tests, shell syntax and one iMac runtime smoke pass.

## Verification plan

```bash
/Users/ant013/anaconda3/bin/python3 -m pytest \
  paperclips/tests/test_phase_c_smoke_test.py \
  paperclips/tests/test_fullaudit_assembly.py -v
bash -n paperclips/scripts/lib/_smoke_probes.sh
git diff --check
```

After merge: deploy a clean canary clone to iMac and run one
`smoke-test.sh fullaudit --cleanup-issues`. Create the CEO roadmap issue only
after it succeeds.

## Adversarial review

- **Policy drift:** rejected; the patch reads existing profile-derived agent
  answers, it does not define what an agent may do.
- **Layering drift:** rejected; using workflow role as a Git-policy override
  conflicts with the Thorchain compose model.
- **Parser ambiguity:** bounded by the fixed English probe contract, which
  explicitly asks for `Can` and `Cannot` lists.
- **False pass:** a forbidden token before `Cannot:` remains a failure; tests
  cover both locations.
- **Smaller alternative:** removing forbidden checks would hide a real writer
  boundary, so it is rejected.

Decision `D-001`: ACCEPT — parser-only correction is the smallest change that
uses the existing, already-developed Paperclip fragments faithfully.
