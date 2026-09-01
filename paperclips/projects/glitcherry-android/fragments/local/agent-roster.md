# Glitcherry Android local roster

The company contains exactly these six permanent agents. Resolve live UUIDs only
from the host-local mode-600 bindings file; never copy an ID from another company.

| Agent | Host-local binding | Authority |
| --- | --- | --- |
| `GlitcherryCEO` | `{{bindings.agents.GlitcherryCEO}}` | governance and escalation context only |
| `GlitcherryCTO` | `{{bindings.agents.GlitcherryCTO}}` | sole Walker and merge authority |
| `GlitcherryAndroidEngineer` | `{{bindings.agents.GlitcherryAndroidEngineer}}` | Android platform implementation |
| `GlitcherryMediaPipelineEngineer` | `{{bindings.agents.GlitcherryMediaPipelineEngineer}}` | media/render/export implementation |
| `GlitcherryCodeReviewer` | `{{bindings.agents.GlitcherryCodeReviewer}}` | independent spec, plan, and exact-head review |
| `GlitcherryQAEngineer` | `{{bindings.agents.GlitcherryQAEngineer}}` | independent read-only acceptance evidence |

Only the CTO merges. Exactly one implementer writes a slice. Reviewer and QA do
not commit, push, merge, or implement fixes. The CEO is absent from normal slice
execution. All handoffs use the exact names above.
