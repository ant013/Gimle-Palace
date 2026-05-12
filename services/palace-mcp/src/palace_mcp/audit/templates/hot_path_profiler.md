## Runtime Hot Paths

{% if findings %}
*{{ findings | length }} function{{ 's' if findings | length != 1 else '' }} found (capped at {{ max_findings }}).*

| Severity | Trace | Function | CPU Share | Wall Share | Samples | Wall ms | Source |
|----------|-------|----------|-----------|------------|---------|---------|--------|
{% for f in findings %}
| {{ f._severity | upper }} | `{{ f.trace_id }}` | `{{ f.qualified_name }}` | {{ "%.2f%%" | format((f.cpu_share | float) * 100.0) }} | {{ "%.2f%%" | format((f.wall_share | float) * 100.0) }} | {{ f.cpu_samples }} | {{ f.wall_ms }} | `{{ f.source_format }}` |
{% endfor %}
{% else %}
No findings — extractor `hot_path_profiler` ran at `{{ run_id }}`{% if completed_at %} on {{ completed_at }}{% endif %},
returned 0 hot-path entries above threshold.
{% endif %}

*Provenance: run `{{ run_id }}`{% if completed_at %}, completed {{ completed_at }}{% endif %}.*
