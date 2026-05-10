# Paperclip project assembly manifests

This directory contains project-level assembly metadata. Keep shared capability
lists here, not duplicated in every generated agent bundle.

## Repeatable setup for a new project

1. Copy `paperclips/projects/_template/paperclip-agent-assembly.yaml` to:

   ```text
   paperclips/projects/<project-key>/paperclip-agent-assembly.yaml
   ```

2. Fill `project.key`, `project.display_name`, and the real project paths.

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
   python3 paperclips/scripts/build_project_compat.py --project <project-key>
   python3 paperclips/scripts/validate_instructions.py --repo-root .
   python3 paperclips/scripts/generate_assembly_inventory.py --check
   bash paperclips/validate-codex-target.sh
   python3 -m pytest paperclips/tests/test_validate_instructions.py
   ```

6. Before deploying a regenerated agent, snapshot the current live `AGENTS.md`
   and compare it with the generated bundle:

   ```bash
   set -a
   source <project-env-file>
   set +a
   python3 paperclips/scripts/compare_deployed_agents.py \
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

Generated agent bundles should change only when role text, overlays, or target
runtime text changes. Project-level capability metadata alone should not add
repeated lines to every bundle.
