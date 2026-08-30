# Semantic Equivalence Report

- Result: `SEMANTIC_EQUIVALENCE_PASSED`
- Baseline: `/tmp/ragwarrant-pre-rename-semantic-baseline.json`
- Current primary outcome: `artifacts/public_mini_reproduction/primary_outcome_statistics.json`
- Intentional suite rename: `ragtune_public_mini_reproduction_v1` -> `ragwarrant_public_mini_reproduction_v1`

## Compared Fields

- `result_class`: baseline `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`; current `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`; match `True`
- `selected_policy`: baseline `risk_guarded_governance`; current `risk_guarded_governance`; match `True`
- `baseline_policy`: baseline `expanded_quality_policy`; current `expanded_quality_policy`; match `True`
- `quality_delta`: baseline `-0.008`; current `-0.008`; match `True`
- `cost_delta`: baseline `-1.3`; current `-1.3`; match `True`
- `example_count`: baseline `4`; current `4`; match `True`
- `policy_count`: baseline `4`; current `4`; match `True`
- `unsafe_low_cost_policy_blocked`: baseline `True`; current `True`; match `True`
- `raw_external_data_used`: baseline `False`; current `False`; match `True`
- `raw_text_exported`: baseline `False`; current `False`; match `True`
- `requires_crag_raw_data`: baseline `False`; current `False`; match `True`
- `requires_generator_credentials`: baseline `False`; current `False`; match `True`
- `requires_hotpotqa_raw_data`: baseline `False`; current `False`; match `True`
