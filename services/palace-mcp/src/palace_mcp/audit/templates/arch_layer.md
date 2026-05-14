## Architecture layer violations{% if summary_stats.get('kit_name') %} ({{ summary_stats.kit_name }}){% endif %}

{% if not findings %}
{% if summary_stats.get("rules_declared") %}
No architecture violations found — {{ summary_stats.get("module_count", "?") }} modules indexed; all layer rules pass.

**Rule source:** `{{ summary_stats.get("rule_source", "unknown") }}`
**Provenance:** run_id `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.
{% else %}
No architecture rules declared — {{ summary_stats.get("module_count", "?") }} modules indexed in Neo4j (no rule evaluation possible).

The `arch_layer` extractor ran but found no rule file at
`.palace/architecture-rules.yaml` or `docs/architecture-rules.yaml`.
Module DAG was written to Neo4j. To enable rule evaluation, add a rule file
to the repository. See the runbook at `docs/runbooks/arch-layer.md`.

**Provenance:** run_id `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.
{% endif %}
{% else %}

### Module DAG summary

- **Modules indexed:** {{ summary_stats.get("module_count", "?") }}
- **Manifest edges:** {{ summary_stats.get("edge_count", "?") }}
- **Rules active:** {{ summary_stats.get("rule_count", "?") }}
- **Violations:** {{ findings | length }}
{% if summary_stats.get("parser_warning_count", 0) > 0 %}
- **Parser warnings:** {{ summary_stats.get("parser_warning_count", 0) }} (see Neo4j for detail)
{% endif %}
{% if summary_stats.get("rule_source") %}
- **Rule source:** `{{ summary_stats.get("rule_source") }}`
{% endif %}

### Critical / high

{% set critical_high = findings | selectattr("severity", "in", ["critical", "high"]) | list %}
{% if critical_high %}
{% for f in critical_high %}
- **{{ f.severity | upper }}** [{{ f.kind }}] `{{ f.src_module }}` → `{{ f.dst_module }}` (rule: `{{ f.rule_id }}`, src: `{{ f.source_context | default('other') }}`)
  {{ f.message }}{% if f.evidence %} — *{{ f.evidence }}*{% endif %}
{% endfor %}
{% else %}
*No critical or high severity violations.*
{% endif %}

### Medium / low / informational

{% set medium_low = findings | rejectattr("severity", "in", ["critical", "high"]) | list %}
{% if medium_low %}
{% for f in medium_low %}
- {{ f.severity }} [{{ f.kind }}] `{{ f.src_module }}` → `{{ f.dst_module }}` (rule: `{{ f.rule_id }}`, src: `{{ f.source_context | default('other') }}`)
  {{ f.message }}{% if f.evidence %} — *{{ f.evidence }}*{% endif %}
{% endfor %}
{% else %}
*No medium / low / informational violations.*
{% endif %}

**Provenance:** run_id `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.
{% endif %}
