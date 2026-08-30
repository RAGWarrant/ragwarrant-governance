# Behaviorally Distinct Policy Experiment Plan

## Dataset Path

Primary path: sanitized CRAG mock-API frozen observations from `ragwarrant_crag_mock_api_validation_v1_20260809-165415-92d8c0edd4`.

Evidence class: `public_full_corpus_mock_api_validation_derived_frozen_observation`.

The publication repository does not include raw CRAG question text, raw source documents, raw API responses, or raw licensed data. This phase therefore derives a stronger operating-constraint analysis from the sanitized per-query metrics already included in the public bundle.

## Candidate Policies

- `low_retrieval_single_endpoint`: maps to the prior `top_k_low` behavior and uses one domain endpoint.
- `expanded_retrieval_multi_endpoint`: maps to the prior `top_k_high` behavior and uses two domain endpoints.
- `adaptive_routing_on_insufficient_evidence`: maps to retrieval-confidence gating and varies API calls by query.
- `measured_cost_minimizer_at_quality_floor`: selects the lowest measured-cost policy within the quality floor.
- `measured_latency_minimizer_at_quality_floor`: selects the lowest p95-latency policy within the quality floor.
- `quality_only_best_on_validation`: selects only by validation quality and ignores cost/latency.
- `constrained_quality_optimizer`: maximizes quality subject to explicit deployment constraints.
- `pareto_frontier_selector`: reports nondominated policies without scalar weighted utility.
- `governed_selection`: applies eligibility, quality noninferiority, and measured operating constraints.

## Actual Behavioral Differences

The policy suite must show nontrivial differences in endpoint sets, API-call counts, measured cost, measured latency, context volume, and routing behavior. The experiment fails closed as `BEHAVIORALLY_DISTINCT_POLICY_TEST_FAILED` if those differences are absent.

## Quality Metrics

The quality result class is expected to be `QUALITY_MEASURE_PROXY_PLUS_EVIDENCE` unless a pinned judge or real annotations are present. The metric combines:

- answer-correctness proxy from the parent frozen quality score;
- evidence-support proxy from successful calls and result counts;
- abstention handling;
- answerability handling where available.

This is stronger than endpoint success alone, but it is not human validation and not generative LLM validation.

## Cost Measurement

Cost uses measured `budget_units` from the frozen CRAG mock-API observations. The primary endpoint uses cost directly and does not depend on a small scalar weighted-utility delta.

## Latency Measurement

Latency uses observed per-query `latency_ms` and reports mean, p50, p90, p95, and p99.

## Selection Rules

Quality-only maximizes validation quality and ignores cost/latency. Governed selection requires quality within a predeclared noninferiority margin of 0.01, governance eligibility, zero failure, and measured operating constraints before minimizing cost and latency.

## Statistical Plan

The primary comparison uses paired query bootstrap confidence intervals for final quality, measured cost, latency, and evidence support. Grouped and independent-repeat claims are marked unavailable unless actual grouping or independent repeats are present.

## Claim Boundaries

This phase can support a bounded claim that governance reduced measured operating cost at equivalent proxy-plus-evidence quality on sanitized frozen CRAG mock-API observations. It cannot support RAG Compass superiority, broad governance superiority, production readiness, human validation, generative validation, or official benchmark status.

## Expected Artifacts

- `artifacts/behavioral_policies/`
- `artifacts/quality_measurement/`
- `artifacts/behavioral_governance/`
- `artifacts/baselines/`
- `artifacts/behavioral_governance_repeat/`
- `results/behavioral_governance/`
