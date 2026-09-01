# Glitcherry Android Paperclip company design

Status: final design awaiting explicit approval

Date: 2026-09-01

Repository baseline: `Gimle-Palace@25e531cd91e7b60375801583626b46357f032557`

Implementation branch: `feature/glitcherry-paperclip-company`

Control-plane baseline: `Glitcherry@f3e49439d098b2e818f8beed2b53a4432cc3dd95`

Control-plane design sync: `docs/paperclip-company-agent-roster@9fc67b7d0a1c7d3d4431e6161c69549aac9041b7`

## 1. Outcome

Add a reusable non-release Walker prompt profile, a complete project-specific
Paperclip bundle for Glitcherry Android, and the tests and operator procedure needed
to create the real company safely.

The finished company is named `Glitcherry Android`, uses issue prefix `GLA`, contains
exactly six permanent Codex agents, and remains dormant after bootstrap and canary.
It does not create, select, or execute a product slice until the Human Engineering
Lead explicitly activates one root Walker issue for a human-approved sprint containing
at least one eligible `READY` roadmap slice.

Success means all of the following are true:

1. The CEO has governance authority only and cannot behave as CTO/Walker.
2. The CTO is the only Walker and can take one prepared slice through spec, plan,
   implementation routing, review, QA, `develop` merge, evidence update, and cleanup.
3. No Paperclip agent has instruction authority to cut a release, sign, publish,
   change a future roadmap, or receive the Human Engineering Lead's full `.env`.
4. Android platform work and media/render/export work have separate implementation
   owners, but only one implementation owner writes a slice at a time.
5. Spec, plan, architecture-aware code review, and QA remain independent from
   implementation through the permanent Code Reviewer and QA roles.
6. The bundle is reproducible, host paths and UUIDs remain host-local, runtime
   instructions contain no unresolved templates, and live smoke verifies authority.
7. Bootstrap is idempotent and journaled; disposable canary issues are removed and no
   feature/root roadmap issue remains after validation.

## 2. Authority model

The authority chain is intentionally not the ThorChain outer-Walker model:

```text
Human Product Owner / Human Engineering Lead + AI assistant
  writes and changes stages, sprints, roadmap slices, owner decisions and releases
                              |
                              v
GlitcherryCEO
  preserves goal, product boundary and escalation context; no normal slice work
                              |
                              v
GlitcherryCTO (single Walker)
  selects only the first eligible READY slice and owns its execution state machine
                              |
             +----------------+------------------+
             |                |                  |
             v                v                  v
Code Reviewer          one implementer      exact-head review -> QA
(spec + plan)          per slice
```

The Human Engineering Lead remains the only owner of:

- roadmap creation, ordering, future-slice changes and `DRAFT -> READY`;
- product and architecture decisions not already resolved by a slice;
- stage acceptance, budgets and company administration;
- release builds, signing, Play Console and publication;
- release credentials, SSH administration and destructive Git operations outside the
  exact, proven-merged task/status branch cleanup defined by this workflow.

The CEO is not a roadmap author, outer Walker, technical planner, merger, or release
manager. The CEO is absent from the normal slice handoff chain. The CTO escalates to
the CEO only for company-boundary conflicts and to the Human Engineering Lead for any
product/roadmap/human-only decision.

## 3. Assumptions and observed preflight

- Both private repositories exist and use `develop` as their integration branch:
  `ant013/Glitcherry` and `ant013/Glitcherry-Android`.
- The canonical roadmap remains only in the control repository. Android specs, plans,
  code, tests, and PR evidence live in the Android repository.
- The Android roadmap is still entirely `DRAFT`. Company creation therefore cannot
  accidentally start a valid feature slice unless a human first changes the roadmap.
- The live Paperclip API contained no Glitcherry company on 2026-09-01. Prefix `GLA`
  was unused by the observed active and archived companies.
- The iMac does not yet have either Glitcherry source clone under the intended Android
  paths. They must be created after approval.
- `/Users/Shared/Ios/Gimle-Palace` was at `6d736a4e` with 15 dirty entries during the
  preflight. It is evidence only and must not be pulled, cleaned, or used to deploy this
  change. Deployment uses a fresh worktree from the merged `origin/develop`.
- The iMac has `/Users/Shared/Ios/gimle-skills`; Android SDK/JDK/Maestro and AVD 29/34/36
  are already documented and verified in the control repository.
- `codebase-memory` has no Glitcherry indexes yet. Before live smoke, both local clean
  repositories will be indexed and their exact ready project IDs verified. Intended
  IDs are `Users-ant013-Data-AI-Glitcherry-Android` and
  `Users-ant013-Data-AI-Glitcherry`; the returned IDs, not an assumed slug, become the
  manifest values.
- The current Gimle/Palace MCP was unavailable in this design session and the existing
  codebase-memory Gimle index points to a stale checkout. Every load-bearing framework
  claim was therefore rechecked with Serena and targeted `rg` at the exact baseline.
- Current Paperclip behavior was rechecked in the local fork at
  `paperclip@584cb258c844a90db4ebfbd8fc09418572d26ae7`: supported issue statuses include
  `blocked`; `parentId` and replace-all `blockedByIssueIds` are first-class; completed
  blockers/direct children emit `issue_blockers_resolved` and
  `issue_children_completed`; monthly legacy enforcement applies only above zero.

## 4. Scope

### Reusable framework change

Add a ninth prompt profile named `walker`. It is the reusable capability set for a
technical orchestrator who writes spec/plan changes, pushes task branches, performs an
integration merge after independent gates, and never cuts a release.

The profile extends `reviewer` and adds existing fragments for:

- `git/commit-and-push.md`;
- `worktree/active.md`;
- `pre-work/existing-field-semantics.md`;
- `universal/cto-merge-authority.md`;
- `plan/producer.md`.

It deliberately excludes `git/release-cut.md`. Project role craft and common overlay
further restrict its merge authority to PRs whose base is exactly
`{{project.integration_branch}}`. It cannot approve its own spec, implementation, or
QA evidence even though the inherited reviewer capability teaches review mechanics.

The reusable profile deliberately does **not** include
`handoff/phase-orchestration.md`. That fragment hard-codes the older Gimle
plan-first flow, a separate architect reviewer and a release-cut handoff. The
project's `WORKFLOW.md` and CTO role craft are the only phase authority for
Glitcherry. Rendered-prompt tests reject the conflicting `Plan-first review`,
`architect reviewer`, `Phase 3.2` and `release-cut planned` markers.

`bootstrap-project.sh` gains a `walker` profile dispatch case. Runtime smoke gains:

- must have: `fetch`, `commit`, `push`, `merge`;
- must not have in the `Can` section: `release-cut`, release branch, tag or publish;
- normal atomic handoff probe;
- workflow identity remains independent and is `inner_orchestrator` for the CTO.

The existing `cto` profile and its release semantics remain unchanged for established
companies.

### Project bundle

Add `paperclips/projects/glitcherry-android/` with an exact assembly, workflow, local
examples, common Codex overlay, local roster fragment and six custom role crafts.
Build and commit the resolved assembly and six rendered `AGENTS.md` artifacts.

### Live bootstrap

After the implementation is merged to Gimle-Palace `develop`:

1. create clean iMac source clones at `/Users/anton/Android/Glitcherry` and
   `/Users/anton/Android/Glitcherry-Android`;
2. create a fresh Gimle deploy worktree from the merged `origin/develop`;
3. create mode-`600` host-local `paths.yaml` and generated `bindings.yaml` under
   `~/.paperclip/projects/glitcherry-android/`;
4. validate, build and bootstrap with each agent rooted at its persistent workspace;
   run the project workspace preparer to clone the verified GitHub Android upstream
   into each `workspace/repo` and the control upstream into CTO
   `workspace/control`, then run quick smoke and a disposable end-to-end canary;
5. verify exact API state and leave the company with no feature/root roadmap issue;
6. remove the fresh deploy worktree after it is clean and no longer needed.

### Control-plane documentation sync

The Glitcherry review branch already synchronizes the provisional design with the exact
six-role roster, the permanent Media Rendering and Pipeline Engineer rationale,
beta/release on-demand roles, and the corrected Walker/workspace contracts. After the
bundle is implemented and the live canary passes, replace only the remaining bootstrap
placeholders with tested evidence and then resolve owner decision 4. Company existence
or roadmap execution must not be claimed before that verification.

## 5. Non-scope

- Any Android application source or feature slice.
- Changing a roadmap slice from `DRAFT` to `READY` or creating the first execution
  issue.
- Generating future beta or release roadmaps.
- Release build, signing, store metadata, Play Console or publication.
- Giving Paperclip agents the operator `.env`, SSH key, GitHub admin token, release
  keystore or Play credentials.
- A Paperclip Product Manager, roadmap writer, Release Manager or Store Publisher.
- Permanent UX, accessibility, security, analytics, CI or infrastructure roles before
  a prepared slice demonstrates that the permanent team cannot cover the work.
- Running two emulators or two implementation owners concurrently.
- Refactoring established Paperclip projects or changing the existing `cto` profile.

## 6. Exact permanent roster

All agents target Codex and use `gpt-5.6-sol`. High effort is sufficient for bounded
execution roles; the Walker, media specialist and adversarial Code Reviewer use
`xhigh` because quality is prioritized over schedule.

| Agent | Profile | Paperclip identity | Workflow role | Effort | Reports to | Owns | Must never do |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GlitcherryCEO` | `minimal` | `ceo` / `crown` | `governance` | `high` | — | Goal, company boundary, escalation context | Walk roadmap, write spec/plan, implement, review, merge, release |
| `GlitcherryCTO` | `walker` | `cto` / `shield` | `inner_orchestrator` | `xhigh` | CEO | One READY slice, spec/plan authorship, routing, gated merges, status/evidence, cleanup | Change future roadmap, self-review, implement app code, merge to `main`, release/publish |
| `GlitcherryAndroidEngineer` | `implementer` | `engineer` / `code` | `platform_implementer` | `high` | CTO | Compose/app scaffold, import, state, MediaStore/share, platform integration, build/tooling | Own GPU/effect/codec design without Media review, self-review, merge/release |
| `GlitcherryMediaPipelineEngineer` | `implementer` | `engineer` / `atom` | `media_implementer` | `xhigh` | CTO | 3D/spatial and temporal rendering, GLSL/AGSL/OpenGL effects, presets, Media3/MediaCodec, audio sync, deterministic export/performance | Change product visual contract, platform scope outside plan, self-review, merge/release |
| `GlitcherryCodeReviewer` | `reviewer` | `engineer` / `eye` | `reviewer` | `xhigh` | CTO | Independent spec/plan review plus exact-head code review, Android/media architecture boundaries, Kotlin correctness, lifecycle/concurrency, regression and test quality | Implement fixes, approve hidden product decisions, review a stale head, merge, release |
| `GlitcherryQAEngineer` | `reviewer` | `qa` / `bug` | `qa` | `high` | CTO | Acceptance evidence, unit/lint, sequential AVD, Compose UI, Maestro, media fixtures and physical-device gate | Commit/push/fix production code, waive failures, run concurrent emulators, merge/release |

QA intentionally composes the non-writing `reviewer` capability profile and receives
its smoke/evidence contract from the Glitcherry QA role craft. The established `qa`
profile extends `implementer` and explicitly advertises `commit push`; using it while
claiming that QA cannot push would create two contradictory authority layers.

### Why the custom permanent Media role is required

The technical prototype is not primarily a CRUD or standard Compose application. Its
highest-risk path is deterministic spatial/temporal rendering plus photo/video export,
hardware codec behavior and audio synchronization. Combining that work permanently
with general Android platform ownership creates one broad implementer who would both
choose and implement the most consequential boundary. A dedicated media implementer:

- gives render/export slices a clear owner;
- lets the platform engineer focus on Android lifecycle, import, storage and UI shell;
- preserves one-writer-per-slice while allowing the other specialist to provide a
  read-only boundary review;
- makes failures route to a real specialty rather than back to a generic CTO.

This is not permission for two agents to edit the same branch. The CTO assigns exactly
one primary implementer. Cross-domain slices select one owner and request a bounded
read-only finding from the other before code review.

The Media agent is a project-specific Paperclip role, not a new universal Gimle
profile. It composes the reusable `implementer` profile with a Glitcherry role craft.
The role craft owns Android media editing and export rather than generic playback, and
routes platform-only import/storage/share work to the Android Engineer.

### Android vs Media ownership boundary

The split must be decided by the slice's primary acceptance risk, not by who touched a
screen last:

- `GlitcherryAndroidEngineer` owns picker/import flows, file validation, permissions,
  URI persistence, app lifecycle, preview screen state, save/share integration,
  repository wiring, and build/tooling changes.
- `GlitcherryMediaPipelineEngineer` owns `EditedMediaItem`/`Composition` shape,
  effect graph order, custom OpenGL effects, audio processors, encoder/export
  settings, tone-mapping/export policy inside the approved slice, and deterministic
  render/export performance.
- Single-asset preview defaults to `ExoPlayer.setVideoEffects()` or the equivalent
  stable preview path. `CompositionPlayer` is allowed only when the slice truly needs
  multi-asset or shared-`Composition` preview and the spec explicitly accepts its
  early-preview `@ExperimentalApi` status and single-thread access requirement.
- AGSL is an optional Android 13+ (`RuntimeShader`) path for preview or narrowly
  scoped image processing. The baseline prototype/export path must not depend solely on
  AGSL because the product floor is broader than API 33.
- If a slice simultaneously changes import/permission/storage behavior and effect/
  codec/export behavior, the CTO still assigns one primary owner and requests a bounded
  read-only boundary finding from the other specialist before exact-head code review.

The media role stops and escalates instead of guessing when:

- the required preview/export path depends on an unstable API not accepted in the spec;
- the chosen effect path only works on API 33+ but the slice did not declare that
  boundary;
- the input/output format, HDR behavior, or codec compatibility policy is not defined
  by the slice acceptance criteria;
- deterministic fallback is unknown for unsupported hardware, import rejection, or
  export optimization failure.

### External skill/source strategy for the Media role

No single public skill covers the complete Android 3D, effect, codec, audio and export
surface. Implementation therefore creates one reviewed Glitcherry role craft from
multiple narrowly routed sources rather than installing an unreviewed third-party
agent bundle:

- Android's official [Media3 Transformer](https://developer.android.com/media/media3/transformer)
  and [transformations](https://developer.android.com/media/media3/transformer/transformations)
  documentation is the source of truth for editing, effects, MediaCodec/OpenGL
  integration and export. Official
  [CompositionPlayer](https://developer.android.com/media/media3/transformer/compositionplayer),
  [supported formats](https://developer.android.com/media/platform/supported-formats),
  [AGSL](https://developer.android.com/develop/ui/views/graphics/agsl), and
  [Media3 release notes](https://developer.android.com/jetpack/androidx/releases/media3)
  complete the required baseline for preview stability, API-floor guards, format/HDR
  policy, and current dependency versioning.
- [`sunnat629/android-media-pack@1d74b495`](https://github.com/sunnat629/android-media-pack/tree/1d74b4953d21ee31a3acf61eff68972e100c2ac3)
  skills `media3-transformer-editing`,
  `media3-video-effects-lottie-muxer`, `media3-inspector-metadata-thumbnails` and
  `media3-test-utils-robolectric` are useful workflow/checklist inputs, but the
  repository currently advertises Media3 `1.10.1` while the official stable release is
  `1.11.0` (2026-08-05). The pinned source is Apache-2.0. Treat it as a
  checklist/reference source only, never as the version baseline.
- [`MiniMax-AI/skills@60aaae52/shader-dev`](https://github.com/MiniMax-AI/skills/tree/60aaae52bb2af8162732751a4332f62a5fef518b/skills/shader-dev)
  is a useful MIT-licensed GLSL technique library for
  SDF, ray marching, procedural effects, multipass buffers and post-processing. Its
  ShaderToy/WebGL assumptions must be adapted and verified for the selected Android
  OpenGL ES, AGSL or Media3 Effect surface. The upstream repository is explicitly
  marked beta, so only pinned snippets/checklists are acceptable inputs.
- [`krutikJain/android-agent-skills@c5bf6731/android-media-files-sharing`](https://github.com/krutikJain/android-agent-skills/tree/c5bf6731b8441019418784484cca1578413e6ad3/skills/android-media-files-sharing)
  informs the Android
  Engineer's import/export URI and share boundary; it is not the Media agent's core
  render skill and must not drag in unrelated release/CI authority from the broader
  repository.
- Generic FFmpeg command collections may inform host-side fixture inspection, but no
  unlicensed command pack is vendored and FFmpeg never substitutes for the on-device
  Media3/MediaCodec implementation.

External material contributes domain guidance only. It cannot grant Git, Paperclip,
roadmap, merge or release authority. Before any upstream text or asset is copied, the
implementation records repository URL, immutable revision, license, selected files,
Android adaptation delta, allowed responsibility area, and a current official-
documentation freshness check. No role may execute vendor install/update scripts during
normal slice work.

No third-party skill is installed, vendored or invoked by the runtime company in this
change. The pinned files are design evidence from which a small project-owned contract
is distilled. Installing a real external skill later requires its own reviewed spec,
license/source diff and rendered-authority test.

## 7. Roles that are intentionally not permanent

| Candidate role | Decision now | Hiring trigger |
| --- | --- | --- |
| Product Manager / roadmap writer | Never a Paperclip role | Roadmap remains human-owned |
| Release Manager / Store Publisher | Never a Paperclip role | Release and publication remain Human Engineering Lead operations |
| UX + Accessibility Reviewer | On demand for closed beta | First `READY` beta slice with final interaction, onboarding or accessibility acceptance |
| Privacy + Security Reviewer | On demand | Telemetry, sensitive permissions/data flow, billing, external SDK, release hardening or threat-model slice |
| CI / Infrastructure Engineer | On demand | CI, signing-free release-like automation or build farm becomes a dedicated multi-area slice |
| Analytics / Growth | Not planned | Human-approved product requirement after beta evidence |
| Researcher / Technical Writer | Not permanent | A bounded research/docs slice cannot be owned by CTO/reviewer without delaying product flow |

The operator adds an on-demand agent through a new reviewed manifest change. The CTO
must not hire or invent a role dynamically inside a running product slice.

## 8. Instruction assembly by layers

Composition order follows the current builder:

1. **Universal safety floor** — injected by `inheritsUniversal`.
2. **Reusable profile** — capabilities such as review, implementation, QA or Walker.
3. **Glitcherry common overlay** — company authority, two repositories, integration
   branch, one-active-slice rule, no release, evidence and handoff protocol.
4. **Project role craft** — exact mission, inputs, outputs, allowed actions, forbidden
   actions, state transitions, verification and escalation for one named agent.
5. **Generated local roster fragment** — company UUID and exact same-company agent
   bindings; no copied UUIDs from another company.
6. **Repository `AGENTS.md`** — repo-local branch/spec/test policy loaded in the agent's
   Android checkout. The CTO additionally loads the control repository rules before a
   status change.
7. **Canonical roadmap slice** — human-owned scope, acceptance, dependencies and stop
   conditions.
8. **Paperclip issue, technical spec and implementation plan** — execution detail for
   one slice; these may narrow but never expand the roadmap.

Narrower instructions do not override a higher authority boundary. An issue cannot
grant release permission, make the CEO a Walker, let an implementer self-review, or
turn a `DRAFT` slice into executable work.

Within the project layer, `paperclips/projects/glitcherry-android/WORKFLOW.md` is the
single lifecycle authority. Common overlays and all six role crafts link to that file
and explicitly supersede conflicting phase names inherited from reusable fragments.
The rendered bundle must contain one phase graph, not a collection of prose overrides.

Every custom role file uses the same sections:

- identity and single-sentence mission;
- authoritative inputs and required freshness checks;
- owned outputs and observable completion evidence;
- allowed repository/Paperclip actions;
- explicit forbidden actions;
- accepted inbound state and exact next owner(s);
- retry/review ceiling and escalation destination;
- ownership classifier: route to Android owner when the primary risk is lifecycle,
  permissions, import, storage/share, app state, or build wiring; route to Media owner
  when the primary risk is effect graph, codec, export, audio processing, HDR/format
  policy, or deterministic rendering;
- source lockbox: official source URLs, last-reviewed date, pinned upstream revision,
  license, selected excerpts/files, and Android adaptation notes for any borrowed
  public skill;
- explicit stop conditions for unstable APIs, unsupported media formats, API-floor
  mismatches, hardware capability gaps, and undefined fallback behavior;
- disposable `smoke-probe-*` / `smoke-e2e-*` exception that forbids product work;
- atomic handoff: POST evidence -> require 2xx -> PATCH assignee/status -> one GET
  verification -> STOP.

No role file contains a live UUID, token, absolute operator path or release secret.
Bindings and host paths are rendered from mode-`600` host-local files.

## 9. Slice workflow

CEO is not part of the normal chain.

### Parent Walker loop

The Human Engineering Lead creates or explicitly activates one root issue whose
description pins the approved sprint identifier, ordered slice IDs and control
`ROADMAP.md` head SHA. The CTO may execute only that pinned set; it cannot silently
continue into another sprint.

On every parent wake, CTO fetches the control repository and verifies all of these
before selection: no non-terminal direct child, no unresolved `blockedBy`, no task or
status branch residue, no approved-but-unmerged PR, no dirty persistent repository and
no orphaned temporary worktree. It then selects the first pinned `READY` slice whose
dependencies are `DONE`.

For a selected slice CTO creates exactly one issue with `parentId=<root-id>`, verifies
the parent/child relation, then PATCHes the parent to `status=blocked` with
`blockedByIssueIds=[<child-id>]`. This uses the current Paperclip dependency contract,
not Trading's old prose-only `relatedWork.outbound` convention. When the child reaches
`done`, Paperclip wakes the parent with `issue_blockers_resolved` and/or
`issue_children_completed`; CTO clears the resolved blocker, verifies cleanup again and
performs the next scan. If the automatic wake is absent, watchdog may issue one bounded
recovery wake and CTO polls the exact child once. It never creates a second child as a
recovery mechanism.

If all pinned sprint slices are `DONE`, CTO posts the sprint execution summary and
marks the root `done`; this does not accept the product stage or start the next sprint.
If unfinished pinned work exists but no slice is eligible, the root becomes
`blocked` with reason code `ROADMAP_BLOCKED`, the exact Human Engineering Lead action,
and no autonomous selection outside the pinned sprint.

### Seven child phases

1. **Spec — CTO.** From a clean persistent Android clone, fetch/prune, fast-forward
   local `develop`, create `feature/GLA-N-<slug>`, write only the materialized technical
   spec and push the spec-only commit. Set the child `in_review` and assign Code
   Reviewer. The spec may narrow but never expand the human slice.
2. **Independent spec review — Code Reviewer.** In a fresh wake, fetch the exact spec
   head, review feasibility, Android/media boundaries, hidden product decisions and
   testability, then restore the reviewer clone to clean current `develop`. Approval is
   evidence tied to the immutable head; findings return to CTO.
3. **Plan plus independent plan review — CTO -> Code Reviewer.** CTO writes and pushes
   the traceable test/implementation/commit plan. Code Reviewer checks the exact head
   without implementing. Maximum two spec/plan revision rounds; unresolved disagreement
   blocks the child for the Human Engineering Lead.
4. **Implementation — exactly one engineer.** CTO chooses Android or Media by primary
   acceptance risk. The assigned engineer fetches the approved branch, implements,
   runs tests, pushes only that task branch and opens/updates its PR. Before handing
   off, the engineer switches its persistent clone back to clean `develop` but retains
   the local task ref until the squash merge is proven. The other implementer remains
   on `develop`; reviewers and QA never push; only CTO merges.
5. **Exact-head code and architecture review — Code Reviewer.** In a fresh wake, review
   the exact PR head and mechanical checks. High-risk media/platform changes receive
   the explicit architecture/media lens, including experimental API, AGSL API-floor,
   codec/HDR/fallback and preview/export parity checks. Code defects return to the same
   implementer; plan/scope gaps return to CTO. Every new head invalidates prior review.
   Maximum two implementation review loops.
6. **QA — QA Engineer.** Fetch the exact reviewed head in detached read-only state,
   run risk-scaled gates and only one AVD at a time, post command/result/artifact
   evidence, then restore the clone to clean current `develop`. Media slices cover one
   normal and one approved degraded path.
7. **Integrate, synchronize and clean — CTO.** Verify the exact head, PR base
   `develop`, required checks, Code Reviewer approval and QA PASS; squash-merge Android
   and record its immutable merge SHA on the child. In the persistent control clone,
   first search `origin/develop` for the unique `GLA-N + Android merge SHA` marker. If
   absent, create one status branch, change only status/evidence/required ADR index,
   push and squash-merge it; if present, skip duplicate control work. After both merge
   SHAs are proven, run the bounded cleanup handoff to the primary implementer, clean
   CTO's two clones, verify all phase-owner evidence, and only then mark the child
   `done`.

QA routing is deterministic:

| Observation | Child transition |
| --- | --- |
| All required checks and acceptance evidence pass on the exact head | `in_progress` -> CTO for Phase 7 |
| Reproducible implementation/build/test/device defect | `in_progress` -> the same implementer; prior review/QA invalid |
| Scope drift, missing acceptance, spec/plan mismatch or undefined fallback | `in_progress` -> CTO; revise spec/plan and repeat independent gates |
| Physical-device-only, owner-decision or credential/capability blocker | `blocked` with named Human Engineering Lead action; no next child |
| Local infrastructure residue or transient iMac failure | `blocked` with reason `LOCAL_BLOCKED`; bounded recovery on the same child |

`LOCAL_BLOCKED` and `ROADMAP_BLOCKED` are evidence reason codes, not invented
Paperclip statuses; the API status is `blocked`. Neither reason permits parking the
child and starting another.

If Android merged but control integration or cleanup failed, recovery starts from the
recorded Android SHA, checks whether the unique control marker already landed, and
finishes only the missing control/cleanup/finalization steps. It never recreates or
re-merges implementation and never scans for another slice.

Every handoff is evidence POST -> require 2xx -> PATCH assignee/status -> exactly one
read-only verification -> STOP. A mention is decoration, not a wake contract. On HTTP
409, reload once and enter the explicit recovery path instead of retrying a wake loop.

## 10. Workspace, repositories and runtime policy

Committed examples use `/opt/example/...`; real values remain in:
`~/.paperclip/projects/glitcherry-android/paths.yaml`.

Expected live layout after approval:

```text
/Users/anton/Android/Glitcherry-Android              clean Android source clone
/Users/anton/Android/Glitcherry                      clean control source clone
/Users/anton/Android/glitcherry-paperclip-runtime    non-repository runtime root
/Users/anton/Android/glitcherry-paperclip-runs/
  <Agent>/workspace/AGENTS.md                        generated role instructions
  <Agent>/workspace/repo/AGENTS.md                   tracked Android repo rules
  <Agent>/workspace/repo                             persistent Android clone
  GlitcherryCTO/workspace/control                    persistent CTO-only control clone
```

Assembly sandbox contract:

- `mode: constrained`;
- `bypass_approvals_and_sandbox: false` unless live canary proves required GitHub and
  local tool operations cannot work; any change to `true` requires a revised spec;
- do **not** set `workspace_git_source_path_key`: current bootstrap would make
  `workspace/repo` the runtime cwd and overwrite its tracked `AGENTS.md` with the
  per-agent prompt, making every Glitcherry-Android clone dirty before work begins;
- runtime cwd stays the persistent `workspace` root and generated role instructions
  stay at `workspace/AGENTS.md`; project Git commands operate only in `workspace/repo`;
- after dormant bootstrap and before any agent wake, the idempotent project workspace
  preparer clones the allowlisted GitHub upstream directly into `workspace/repo` and
  never uses a local path as `origin`;
- only `PAPERCLIP_API_URL` is injected and must be loopback HTTP;
- the default per-agent workspace and scratch are writable;
- the source clone and other reference roots are not shared writable workspaces;
- no `.env`, GitHub token, SSH key, keystore or Play credential is injected;
- CTO creates/updates only its sibling `workspace/control` checkout;
- all other agents use the Android checkout and GitHub/codebase-memory for read-only
  control context;
- emulator execution is globally sequential on the 4-core iMac.

Persistent `workspace`, `workspace/repo` and CTO `workspace/control` directories are
never removed between slices. Normal slice execution rotates branches inside these
clones and does not create an ephemeral `git worktree`. If an approved recovery step
does create an exact temporary worktree, its absolute path and owning branch are
recorded first and that temporary path alone is removed after merge.

Reviewers and QA fetch an immutable head in detached state and restore current clean
`develop` before handoff. The primary implementer also restores `develop` before
review, but keeps the local task ref until merge. After squash merge, cleanup verifies
the recorded PR head, absence of unpushed work and remote deletion before force-
deleting that exact local task ref; this exception is necessary because squash commits
are not ancestors of `develop`. No broad branch glob or workspace deletion is allowed.

If constrained mode blocks a required operation, the canary fails. The implementation
must first narrow the missing writable/read-only root or command. It must not silently
switch to unrestricted execution.

## 11. Model, concurrency and cost policy

- Model: `gpt-5.6-sol` for all six agents.
- Reasoning: exact efforts in the roster table.
- One product parent issue and at most one non-terminal child slice may be active.
- One implementation owner may have the task branch checked out writable at a time;
  all other persistent clones remain clean `develop` or detached read-only review.
- Review agents run after a pushed checkpoint; they do not write concurrently.
- One Android emulator workload runs at a time; AVD 29, 34 and 36 are sequential.
- CEO wakes only for an escalation or explicit governance check.
- Bootstrap currently creates company/agent `budgetMonthlyCents: 0`; current Paperclip
  enforces legacy monthly limits only when the value is greater than zero. Therefore
  zero means no hard cap, not a safe zero-spend pause. Dormant creation may retain zero,
  but first root activation requires verified positive company and per-agent caps plus
  an alert threshold recorded by the Human Engineering Lead.

## 12. Files and areas affected

### Gimle-Palace framework

- `paperclips/fragments/profiles/walker.yaml` — new reusable non-release profile.
- `paperclips/scripts/bootstrap-project.sh` — recognize `walker` fallback identity.
- `paperclips/scripts/lib/_smoke_probes.sh` — Walker Git capability contract.
- `paperclips/tests/test_phase_b_profiles.py` — exact nine-profile inventory and Walker
  extends/includes/no-release assertions.
- `paperclips/tests/test_phase_c_smoke_test.py` — structural Walker probe assertions.

No change is planned for `cto.yaml`, `git/release-cut.md`, the manifest role/icon schema,
or canary agent selection.

### New Glitcherry project bundle

- `paperclips/projects/glitcherry-android/paperclip-agent-assembly.yaml`
- `paperclips/projects/glitcherry-android/WORKFLOW.md`
- `paperclips/projects/glitcherry-android/bindings.local-example.yaml`
- `paperclips/projects/glitcherry-android/paths.local-example.yaml`
- `paperclips/projects/glitcherry-android/fragments/local/agent-roster.md`
- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-ceo.md`
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md`
- `paperclips/projects/glitcherry-android/roles-codex/android-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/media-pipeline-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md`
- `paperclips/projects/glitcherry-android/roles-codex/qa-engineer.md`
- `paperclips/projects/glitcherry-android/references/media-skill-sources.md` — immutable
  upstream revisions, licenses, selected guidance and Android adaptation deltas.
- `paperclips/projects/glitcherry-android/scripts/prepare-runtime-workspaces.sh` —
  idempotently clone/verify direct GitHub Android repos under every persistent
  workspace plus the CTO control repo without overwriting tracked `AGENTS.md`.
- `paperclips/tests/test_glitcherry_android_assembly.py`
- `paperclips/tests/test_glitcherry_android_runtime_workspaces.py`
- generated `paperclips/dist/glitcherry-android.resolved-assembly.json`
- generated six files under `paperclips/dist/glitcherry-android/codex/`.

No custom Codex subagent TOML files and no installed third-party skills are planned.
The project-owned Media role craft cites the audited source record; it does not depend
on hidden workers, vendor installers or ambient skill availability.

### Glitcherry control repository design sync

- `docs/runbooks/paperclip-android-team.md`
- `docs/runbooks/walker-lifecycle.md` only where the exact routing/loop contract needs
  synchronization
- `docs/research/paperclip/instruction-layering.md` for the final layer table and custom
  role authoring checklist
- `ROADMAP.md` execution-state clarification is already on the review branch; owner
  decision 4 and the evidence log change only after live canary succeeds
- `README.md` only if links/status text requires synchronization.

## 13. Component analog and delta matrix

| Behavioral slice | Primary spine | Supporting/counterexample | Preserved | Deliberate Glitcherry delta | Test before code |
| --- | --- | --- | --- | --- | --- |
| Non-release CTO Walker profile | `reviewer.yaml` plus current profile composer | Bootstrap/smoke profile dispatch; reject `cto.yaml` release-cut and generic phase-orchestration | Universal safety, discovery, review/plan mechanics, handoff, merge gates | New `walker` adds commit/push/worktree/merge/plan, excludes release-cut and hard-coded project phases; Glitcherry workflow restricts merge to `develop` | Add failing inventory/includes/no-release/no-legacy-phase tests and runtime marker assertions before profile/script edits |
| Glitcherry Android company bundle | ThorChain assembly, custom role files, workflow and exact project test | Trading single Code Reviewer idea; current Paperclip `parentId`/`blockedByIssueIds`; fullAudit constrained sandbox; reject legacy relatedWork and release-capable CEO/CTO | Portable manifest, host-local bindings, explicit identity, generated prompts, one active child, atomic handoff, dormant bootstrap | CEO governance; CTO sole Walker; six roles including Media; QA uses non-writing reviewer profile; seven child phases; two repos; `develop`; one writer/emulator | Add failing exact roster/authority/phase/wake/QA-routing/dormancy/render assertions, then create bundle until green |
| Dormant bootstrap and canary | Journaled `bootstrap-project.sh` create-or-reuse lifecycle | Smoke/rollback disposable issue family; tracked Android `AGENTS.md` is a counterexample to cwd=`workspace/repo`; quarantine dirty shared iMac checkout | Prefix collision guard, idempotent bindings, persistent per-agent workspaces, managed config reconciliation, disposable issue cleanup | Keep cwd and generated role prompt at workspace root; direct GitHub clones under `./repo`; tracked repo `AGENTS.md` untouched; CTO control clone; no root issue | Run static bootstrap/smoke/workspace-preparer tests; then live exact cwd/clean/origin/API assertions and disposable CTO->CodeReviewer handoff |

## 14. Verification plan

### Static and local

Run from the fresh Gimle implementation worktree:

```bash
python3 -m pytest \
  paperclips/tests/test_phase_b_profiles.py \
  paperclips/tests/test_phase_c_smoke_test.py \
  paperclips/tests/test_glitcherry_android_assembly.py \
  paperclips/tests/test_glitcherry_android_runtime_workspaces.py
bash -n paperclips/scripts/bootstrap-project.sh
bash -n paperclips/scripts/lib/_smoke_probes.sh
bash -n paperclips/projects/glitcherry-android/scripts/prepare-runtime-workspaces.sh
bash paperclips/scripts/validate-manifest.sh glitcherry-android
bash paperclips/build.sh --project glitcherry-android --target codex
python3 -m paperclips.scripts.validate_instructions --repo-root .
```

Project tests assert:

- exact six names, reports-to graph, model, effort, profile, icon and workflow role;
- CEO `minimal`, CTO `walker`, exactly one `inner_orchestrator`;
- no `outer_walker`, no second CTO/Walker and no release/profile authority on CEO;
- constrained sandbox, workspace-root cwd and host path contract;
- both codebase-memory project IDs render and no `{{...}}` remains;
- required role/overlay/workflow/example files exist;
- the media source record pins revision/license and the custom role routes each source
  without inheriting external authority or executable scripts;
- the rendered media role contains an ownership classifier, version/license/source
  lockbox, `CompositionPlayer` experimental guard, and AGSL API-33 guard;
- the assembly omits `workspace_git_source_path_key`; generated role `AGENTS.md` stays
  outside the repo; tracked Android `AGENTS.md` is byte-identical and Git status clean;
- the workspace preparer is idempotent, refuses unmanaged/dirty/wrong-origin targets,
  and clones only the verified GitHub upstream before any agent wake;
- normal workflow excludes CEO, has one Code Reviewer for spec/plan/code, and has one
  implementation owner;
- QA composes `reviewer`, cannot commit/push, and has an exact routing table;
- parent/child state uses `parentId` plus `blockedByIssueIds`, handles both current wake
  reasons, forbids a second non-terminal child and forbids advancing after blocker,
  partial merge or incomplete cleanup;
- rendered CTO/reviewer prompts contain no plan-first, architect-reviewer, Phase 3.2 or
  release-cut-planned state machine;
- POST -> PATCH -> one verification -> STOP and bounded review loops are present;
- bootstrap creates no roadmap/product issue and activation is human-only;
- rendered CEO lacks merge/plan/release instructions;
- rendered CTO contains Walker/select/spec/plan/merge/cleanup duties but no actionable
  release-cut, tag, `develop -> main`, signing or publishing authority;
- implementers cannot merge/self-review; reviewers cannot implement; QA cannot fix or
  waive product failures.

### Codebase-memory preflight

Index both clean local repositories, wait for `ready`, record exact IDs, and replace an
intended ID if the tool returns a different canonical name. Search each by a known
document anchor to prove the index is usable. This is performed before the live build
so rendered instructions never ship a guessed project identity.

### Git and integration

Push the implementation branch, open a PR to Gimle-Palace `develop`, wait for required
checks, then squash-merge. A separate human review is not required for this single-owner
workspace, but CI and the approved spec remain mandatory. Confirm the squash SHA is on
`origin/develop` before any iMac deployment.

### Live iMac bootstrap

1. Verify API health, Paperclip authentication, `gh auth`, free disk and required
   Android/Gimle paths without printing secrets.
2. Clone or fast-forward the two dedicated clean product sources; refuse dirty sources.
3. Create a fresh deploy worktree from the merged Gimle `origin/develop`.
4. Write host-local paths with mode `600`; verify the committed examples contain no
   actual host UUID/path/secret.
5. Build and inspect all rendered prompts before API mutation.
6. Run bootstrap without a feature activation command.
7. Run the workspace preparer before any agent wake. Verify every adapter cwd is the
   workspace root, every generated role prompt is outside the repo, every Android clone
   has the allowlisted GitHub origin/current `develop`/clean status, and the tracked
   Android `AGENTS.md` hash matches the source repository. Verify the CTO control clone
   the same way.
8. From the same host credential context, run `git ls-remote` against both private
   origins and query GitHub repository permission showing `push=true`; do not create a
   remote branch merely to test auth. Then run `smoke-test.sh glitcherry-android
   --quick --cleanup-issues` and the disposable `--canary-stage=2 --cleanup-issues`
   CTO-to-CodeReviewer handoff.
9. Delete every disposable issue and verify no feature/root roadmap issue exists.
10. Query the API and assert exactly one `Glitcherry Android` company with prefix `GLA`,
    exactly six agents, exact hierarchy/adapter/model/effort/cwd, and no forbidden env.
11. Verify agents are idle after canary, watchdog contains no duplicate/error wake, and
    all host-local binding files are mode `600`.
12. Remove the clean deploy worktree and prune; preserve all unrelated iMac checkouts.

Any failed live assertion stops activation. Journal rollback targets only resources
created by this bootstrap; it must never delete an existing company, unrelated agent,
source clone or dirty checkout.

## 15. Acceptance criteria

- A reusable `walker` profile exists, validates, composes and is runtime-probed as
  commit/push/merge capable and release-incapable.
- The existing `cto` profile and all established project assemblies remain green.
- The committed Glitcherry manifest and generated artifacts contain exactly the six
  approved agents and no host-specific path, secret, live UUID or unresolved template.
- The role graph and workflow match sections 6 and 9 exactly.
- QA is display/workflow role `qa` but composes non-writing `reviewer`; its rendered
  `Can` section contains no commit or push.
- Every adapter cwd is its persistent workspace root, generated instructions remain
  outside the Git checkout, and every tracked repository `AGENTS.md` stays unchanged.
- The company is created once, prefix `GLA` is unique and bootstrap re-run is idempotent.
- Each live agent answers its profile/workflow smoke within the bounded timeout.
- The disposable CTO -> Code Reviewer handoff has successful evidence POST,
  assignment PATCH, one verification and STOP, with no duplicate wake.
- All disposable smoke issues are removed or terminal and no product/root issue exists.
- No adapter env contains operator/release/SSH/GitHub secrets; only the loopback
  Paperclip URL is project-injected.
- Both source repos and all unrelated iMac worktrees retain their prior content; the
  dirty shared Gimle checkout is untouched.
- Control docs record the verified roster and company bootstrap evidence without
  copying secrets or claiming roadmap execution has started.

## 16. Failure modes and stop conditions

| Failure | Required response |
| --- | --- |
| `GLA` becomes allocated before bootstrap | Stop and revise the spec/prefix; do not reuse another company |
| Existing company name with different bindings | Stop; inspect exact company and journal, never attach by name alone |
| CEO prompt contains merge/plan/Walker/release markers | Fail build/test; fix composition before deploy |
| CTO prompt contains release-cut, tag, `main` merge, signing or publish authority | Fail build/test; no live bootstrap |
| Rendered prompt contains plan-first/architect-reviewer/Phase 3.2 legacy flow | Fail build/test; remove the conflicting reusable phase source before deploy |
| Two agents claim implementation or two clones have the task branch writable | Set API status `blocked` with reason `ROADMAP_BLOCKED`, preserve evidence and stop both writers |
| Prior child is non-terminal or any task branch/worktree/workspace is dirty | Keep the prior child active, enter bounded recovery and do not create the next child |
| Parent/child lacks `parentId` or exact `blockedByIssueIds` link | Block activation/advance; repair and verify the current relation, never infer it from prose |
| Android merge exists but control merge or cleanup is incomplete | Resume from the recorded Android merge SHA; first search the control marker, never duplicate/re-implement/re-merge/select another slice |
| Review/QA is performed on a stale PR head | Invalidate approval and rerun on the exact head |
| More than two review/fix loops | Stop and escalate with evidence; do not recurse indefinitely |
| Generated role prompt overwrites tracked repo `AGENTS.md` or makes clone dirty | Stop before agent wake; restore from the clean clone and fix workspace-root layout |
| Android/control source or runtime clone is dirty or has local-path/wrong remote/branch | Stop; preserve evidence and repair only the exact managed clone without deleting user work |
| Constrained sandbox blocks a required action | Narrow and review the missing capability; do not enable broad bypass silently |
| Paperclip 409/duplicate wake/agent error | Reload once, stop the current run and follow recovery; no blind retry |
| Disposable issue cannot be deleted/terminalized | Company remains dormant and activation is blocked |
| Disk below operator threshold or AVD already running | Stop emulator work and record blocker |
| Company or any agent budget remains `0` at root activation | Block activation; set and verify positive hard caps and alerts because zero is uncapped |
| codebase-memory ID absent/stale | Reindex and verify, or explicitly fall back to Serena/rg in a revised rendered prompt |
| Any release/operator secret appears in prompt/config/log | Stop, revoke/rotate as applicable and treat as security incident |

## 17. Adversarial design review

The following challenges must be recorded in durable run state before approval:

1. **Can five agents suffice by folding media into Android?** No. The
   3D/render/shader/codec/audio/export surface is the core prototype risk and deserves
   a separate implementation owner. Six agents retain that specialty while removing
   the duplicative permanent Android Architect.
2. **Should CEO use `cto` as ThorChain does?** No. Explicit `paperclip_role: ceo` changes
   display identity, not composed capability. `minimal` prevents release/merge/plan
   bleed and matches the human-approved authority model.
3. **Can CTO keep the existing `cto` profile and rely on prose to avoid release?** No.
   Runtime smoke explicitly teaches and expects `release-cut`; a separate negative
   capability profile is testable and safer.
4. **Is a project-only custom include set smaller than a new profile?** Not reliably.
   Current manifest custom-include parsing is not a proven nested-list contract. A
   tested reusable profile is the smallest coherent framework change.
5. **Does `walker extends reviewer` allow self-review?** Capability is not assignment.
   The role craft forbids self-approval, exact tests enforce independent owners, and
   live handoff proves the next agent. The inherited mechanics are needed for plan
   feedback and merge-readiness interpretation.
6. **Do two implementers create concurrency risk?** Only if ownership is ambiguous.
   Workflow makes one primary writer mandatory; the other may return read-only findings
   and never writes the same branch.
7. **Should QA use the reusable `qa` profile?** No. It extends `implementer` and the
   current runtime probe requires `commit push`, directly contradicting the approved
   no-push QA authority. Glitcherry QA uses `reviewer` plus a project-owned QA
   smoke/evidence role craft; display and workflow identity remain `qa`.
8. **Can the CTO operate two repositories without overwriting repo instructions?** Yes.
   Runtime cwd and generated role `AGENTS.md` remain at the persistent workspace root;
   direct GitHub Android and control clones live below it and retain their tracked
   repository `AGENTS.md` files.
9. **Should all agents be `xhigh`?** No. Quality-critical judgment roles use `xhigh`;
   bounded governance/platform/QA use `high`. Cost ceiling remains a human gate before
   activation.
10. **Should bootstrap immediately start the first DRAFT slice?** No. It would violate
    the roadmap authority and DoR. Canary is disposable and repository-write-free;
    autonomous product work remains dormant.
11. **Is a permanent Android Architect needed beside Code Reviewer?** No. The reusable
    reviewer profile already covers plan review and architectural compliance. The
    custom Code Reviewer owns independent spec/plan review and an explicit architecture
    lens for high-risk changes; unresolved product/architecture decisions escalate to
    the Human Engineering Lead.
12. **Can a public media skill replace the custom Media role?** No. Available skills
    are partial or platform-mismatched. Audited, revision-pinned upstream material may
    supply domain knowledge, but the project role craft remains authoritative for
    Android adaptation, evidence, workflow and forbidden actions.
13. **Can `LOCAL_BLOCKED` park one child and let Walker start another?** No. A second
    child would reuse state while the prior branch/worktree/evidence is unresolved.
    The current child remains active and the parent stops until bounded recovery or a
    Human Engineering Lead decision completes it.
14. **Can generic constrained Git bootstrap create the Android clones?** Not safely for
    this repository. It sets cwd to `workspace/repo` and copies the per-agent prompt to
    `repo/AGENTS.md`, which is already tracked by Glitcherry-Android. The project omits
    that key and prepares direct GitHub clones below workspace root before any wake.
15. **Should Trading `relatedWork.outbound` drive the parent?** No. Current Paperclip
    exposes `parentId`, `blockedByIssueIds`, `issue_blockers_resolved` and
    `issue_children_completed`. Those first-class links are verified and the old prose
    reference is only historical evidence.
16. **Can bootstrap budget `0` act as a safety pause?** No. Current enforcement creates
    budget policy only above zero. Dormant creation is safe because no root exists, but
    autonomous activation requires positive company and agent caps.

## 18. Open questions

There are no blocking design questions for the spec-only gate or dormant company
creation. Before the Human Engineering Lead activates the first `READY` slice, they
must still set:

- the monthly/weekly model budget and alert threshold;
- the minimum free-disk stop threshold for Android device runs;
- the first roadmap owner decision and first slice promoted to `READY`.

Those values are intentionally not guessed by this company-design change.
