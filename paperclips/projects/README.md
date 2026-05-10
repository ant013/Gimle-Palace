# Paperclip project assembly manifests

This directory contains project-level assembly metadata. Keep shared capability
lists here, not duplicated in every generated agent bundle.

## Repeatable setup for a new project

1. Copy `paperclips/projects/_template/paperclip-agent-assembly.yaml` to:

   ```text
   paperclips/projects/<project-key>/paperclip-agent-assembly.yaml
   ```

2. Fill the required project identity and parameter blocks:

   - `project.*` — project key, display/system names, issue prefix, branch, docs
     paths.
   - `domain.*` — project domain labels used by role templates. Use neutral
     values if the project has no wallet target.
   - `evidence.*` — project-specific incident or lesson references used by
     shared lifecycle rules. Use a neutral label such as `project-handoff-lesson`
     when the new project has no historical issue yet; do not keep Gimle `GIM-*`
     refs in another project.
   - `paths.*` — repo roots, production checkout, Codex team root, operator
     memory directory, overlay root, and primary MCP service path.
   - `mcp.service_name`, `mcp.package_name`, and `mcp.tool_namespace` — the
     project MCP service and tool namespace used by templates.

3. Keep `mcp.base_required` unless there is a reviewed runtime exception:

   ```yaml
   mcp:
     base_required:
       - codebase-memory
       - context7
       - serena
       - github
       - sequential-thinking
   ```

4. Add only project-specific capabilities under `mcp.additions`,
   `skills.additions`, or `subagents.additions`. For example, UAudit audit
   roles can add `neo4j` without editing shared role templates.

5. Rebuild and validate from the repository root:

   ```bash
   python3 paperclips/scripts/build_project_compat.py --project <project-key> --inventory update
   python3 paperclips/scripts/validate_instructions.py --repo-root .
   python3 paperclips/scripts/generate_assembly_inventory.py --check
   bash paperclips/validate-codex-target.sh
   python3 -m pytest paperclips/tests/test_validate_instructions.py
   ```

   The build writes `paperclips/dist/<project-key>.resolved-assembly.json`
   with resolved capability metadata, target adapters, role output paths, hashes,
   and sizes. Commit it with the generated bundle updates.

6. Before deploying a regenerated agent, snapshot the current live `AGENTS.md`
   and compare it with the generated bundle:

   ```bash
   set -a
   source <project-env-file>
   set +a
   python3 paperclips/scripts/compare_deployed_agents.py \
     --project <project-key> \
     --source api \
     --target codex \
     --agent cx-cto \
     --snapshot-dir /tmp/paperclip-agent-snapshots \
     --snapshot-label current \
     --show-diff
   ```

   A diff before deploy is acceptable only when it is the reviewed, intentional
   old-live vs new-generated change. After deploying, rerun the same command
   without `--show-diff`; the deployed live bundle must match the generated
   bundle exactly. Add `--agent cto` or `--agent cx-cto` for a single role.

7. Run the project-aware deploy dry-run before any live upload:

   ```bash
   python3 paperclips/scripts/deploy_project_agents.py \
     --project <project-key> \
     --target codex \
     --agent cx-cto \
     --dry-run
   ```

   This wrapper reads `paperclips/dist/<project-key>.resolved-assembly.json`
   and prints the exact target, agent id, source bundle, hash, and size. It does
   not upload; live deploy remains on the existing compatibility scripts until
   manifest-driven deploy is implemented.

Generated agent bundles should change only when role text, overlays, or target
runtime text changes. Project-level capability metadata alone should not add
repeated lines to every bundle.

## Compatibility expectations

- The project manifest is the logical source of truth for project facts.
- Legacy files such as `paperclips/codex-agent-ids.env`,
  `paperclips/deploy-agents.sh`, and `paperclips/update-agent-workspaces.sh`
  remain declared compatibility inputs until deploy tooling is manifest-driven.
- For a pure parameterization change, generated `paperclips/dist/**` output must
  remain byte-identical for the existing project. Run `git diff -- paperclips/dist`
  after rebuilding.
- Project literal inventory must stay at zero for known Gimle-only patterns in
  shared and role source files. Real project values belong in
  `paperclips/projects/<project-key>/paperclip-agent-assembly.yaml` or project
  overlays.
