## Reactive dependency tracer

{% if findings %}
*{{ findings | length }} diagnostic{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Diagnostic code | File | Language | Message |
|----------|----------------|------|----------|---------|
{% for finding in findings %}
| {{ finding._severity | upper }} | `{{ finding.diagnostic_code }}` | {{ finding.file_path or "-" }} | {{ finding.language or "-" }} | {{ finding.message or "-" }} |
{% endfor %}

{% set errors = findings | selectattr("_severity", "equalto", "high") | list %}
{% set warnings = findings | selectattr("_severity", "equalto", "medium") | list %}
{% if errors %}
**Errors ({{ errors | length }}):** reactive graph analysis failed for these files — check helper JSON or extractor logs.
{% endif %}
{% if warnings %}
**Warnings ({{ warnings | length }}):** partial data — reactive graph may be incomplete.
{% endif %}

{% else %}
No reactive diagnostics — extractor `reactive_dependency_tracer` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %} with 0 issues.

If no `ReactiveComponent` nodes are present, ensure `reactive_facts.json` exists at the repo root. The extractor requires a pre-generated Swift helper output file.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
