# Behaviorally Distinct Governance Experiment

## Experiment purpose

This experiment tests whether RAGWarrant governance can make a materially useful promotion decision when candidate policies differ in actual endpoint routing, API calls, measured cost, and measured latency.

## Why the prior CRAG result was insufficient

The prior CRAG mock-API superiority result was driven mainly by configured cost/latency utility at equal raw quality. That made it useful as governance-machinery evidence, but not enough by itself to show a substantively different retrieval strategy.

## Candidate policies and behavioral differences

The policy suite includes low retrieval, expanded retrieval, adaptive routing, cost-aware, latency-aware, quality-only, constrained, Pareto, governed, and static selectors. See `artifacts/behavioral_policies/policy_definitions.md`.

## Dataset and evidence class

Dataset/path: sanitized CRAG mock-API frozen observations from `ragwarrant_crag_mock_api_validation_v1_20260809-165415-92d8c0edd4`. Evidence class: `public_full_corpus_mock_api_validation_derived_frozen_observation`.

## Quality metric

Result class: `QUALITY_MEASURE_PROXY_PLUS_EVIDENCE`. The metric combines the parent answer-quality proxy, evidence support from successful calls/result counts, and abstention handling. It is not human-calibrated and does not use a pinned LLM judge.

## Cost and latency measurement

Cost uses observed `budget_units`; latency uses observed per-query `latency_ms` with p50/p90/p95/p99 summaries.

## Selection rules

Quality-only maximizes validation quality and ignores cost/latency. Governed selection uses a 0.01 quality noninferiority margin, eligibility gates, and measured cost/latency constraints.

## Baselines

The governed selector is compared against quality-only, constrained optimizer, Pareto frontier selector, cost-aware selector, and latency-aware selector.

## Primary endpoint

Primary endpoint result: `GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY`.

## Confirmatory result

Governed winner `low_retrieval_single_endpoint` was equivalent in final proxy-plus-evidence quality to quality-only `optuna_tpe` and had lower measured cost. Final quality delta was -0.0051537115; cost delta was -2.3683887916; latency delta was -86.1388368144 ms.

## Repeat / robustness result

Repeat result: `BEHAVIORAL_GOVERNANCE_DIRECTIONAL_REPEAT` using frozen-observation resplits. This is weaker than independent replication.

## Negative findings

The quality measure remains proxy-plus-evidence, RAG Compass ranked behind the governed winner, and no human, generative, or official platform validation was run.

## Claim boundaries

This supports a bounded governance claim on sanitized frozen CRAG mock-API source/retrieval observations. It does not support RAG Compass superiority, broad governance superiority, production readiness, human validation, generative validation, or official benchmark status.

## Implication for RAGWarrant

The result strengthens RAGWarrant as a governance framework by replacing a weighted-utility-only framing with a predeclared quality-floor and measured operating-cost endpoint.

## Implication for RAG Compass

RAG Compass remains a secondary candidate optimizer. This experiment does not support optimizer superiority.

## Reproduction instructions

Run `python scripts/run_behavioral_governance_experiment.py` from the repository root, then `python scripts/validate_publication_bundle.py` and `pytest`.
