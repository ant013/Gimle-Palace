# Glitcherry Android local roster

The company contains exactly these six permanent agents. Resolve live UUIDs only
from the host-local mode-600 bindings file; never copy an ID from another company.

Paperclip Project: `{{bindings.project_id}}`.

| Agent | Agent binding | Workspace binding | Authority |
| --- | --- | --- | --- |
| `GlitcherryCEO` | `{{bindings.agents.GlitcherryCEO}}` | `{{bindings.workspaces.GlitcherryCEO}}` | governance and escalation context only |
| `GlitcherryCTO` | `{{bindings.agents.GlitcherryCTO}}` | `{{bindings.workspaces.GlitcherryCTO}}` | sole Walker and merge authority |
| `GlitcherryAndroidEngineer` | `{{bindings.agents.GlitcherryAndroidEngineer}}` | `{{bindings.workspaces.GlitcherryAndroidEngineer}}` | Android platform implementation |
| `GlitcherryMediaPipelineEngineer` | `{{bindings.agents.GlitcherryMediaPipelineEngineer}}` | `{{bindings.workspaces.GlitcherryMediaPipelineEngineer}}` | media/render/export implementation |
| `GlitcherryCodeReviewer` | `{{bindings.agents.GlitcherryCodeReviewer}}` | `{{bindings.workspaces.GlitcherryCodeReviewer}}` | independent spec, plan, and exact-head review |
| `GlitcherryQAEngineer` | `{{bindings.agents.GlitcherryQAEngineer}}` | `{{bindings.workspaces.GlitcherryQAEngineer}}` | independent read-only acceptance evidence |

Only the CTO merges. Exactly one implementer writes a slice. Reviewer and QA do
not commit, push, merge, or implement fixes. The CEO is absent from normal slice
execution. All handoffs use the exact agent and workspace binding pair above.
