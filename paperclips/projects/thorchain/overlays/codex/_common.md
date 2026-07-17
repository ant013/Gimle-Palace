## ThorChainKit Runtime Contract

The authoritative product repository is `{{paths.primary_repo_root}}` on
`{{project.integration_branch}}`. Work on exactly one Paperclip child issue at a
time. Bootstrap creates no roadmap issue and no product issue.

### Evidence before repository changes

1. Load `analog-driven-change` and its required `gimle-evidence` companion from
   `{{paths.gimle_skills_root}}`. Never substitute the legacy
   `analog-driven-development` workflow.
2. Query codebase-memory project `{{agent.primary_codebase_memory_project}}`
   first. Activate the exact assigned workspace with Serena, then verify every
   load-bearing candidate with targeted `rg` and Git reads.
3. Use `{{paths.tronkit_repo_root}}`, `{{paths.evmkit_repo_root}}`, and
   `{{paths.unstoppable_ios_repo_root}}` as verified architecture references.
   Load `uw-ios-analog-profile` only when the exact Unstoppable checkout and an
   Unstoppable integration slice are both in scope.
4. Use `{{paths.vultisig_repo_root}}` as Vultisig THOR-specific supporting
   evidence. It is not the primary ownership or lifecycle spine unless a new
   approved design explicitly says so.
5. Persist Gimle evidence under `docs/reports/gimle/`, complete adversarial
   review, push the final spec and plan, and block for explicit user approval
   before implementation.

### Review workers

For adversarial spec review, `ThorChainCodeReviewer` launches three fresh,
bounded, read-only Codex workers in parallel:

- architecture/boundaries;
- security/protocol-safety;
- verification/operability.

They inherit `gpt-5.6-sol` with `xhigh` reasoning, create no Paperclip agents,
and make no repository, issue, or external-system writes. The reviewer owns the
single severity-tagged synthesis.

### Product and acceptance boundaries

- Native THORChain support belongs in this kit; the existing multichain swap
  provider is not reimplemented in the initial slices.
- Maestro acceptance belongs only in the ThorChainKit `iOS Example`.
  Unstoppable Wallet is verified through its adapter/AppTests/manual gates,
  never by applying this kit's Maestro suite to the wallet application.
- Never add `Co-authored-by:` trailers.
- Follow `paperclips/projects/thorchain/WORKFLOW.md` for ownership and handoff.
