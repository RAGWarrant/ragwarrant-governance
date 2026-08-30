# CRAG Mock-API Validation

Parent run: `ragwarrant_crag_mock_api_validation_v1_20260809-165415-92d8c0edd4`

Result: `MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR`

Key facts:

- Validation rows: 431 / 431
- Confirmatory rows: 571 / 571
- API calls: 14,172
- Failure rate: 0.0
- Governed winner: `top_k_low`
- Quality-only winner: `greedy_regression_aware_search`
- RAG Compass rank: 5th
- Governance delta: +0.0010025405
- Bootstrap CI: [0.0010022708, 0.0010028250]
- Win/tie/loss: 571 / 0 / 0
- Sensitivity: governance superior in 14 / 15 settings

Interpretation: this supports RAGWarrant governance value more directly than RAG Compass optimizer superiority.

CRAG raw data, raw question wording, raw source passages, and raw mock-API responses are not included here. Case explanations use sanitized summaries and query hashes rather than CRAG wording. Reproduction requires obtaining CRAG from the original approved source, verifying expected hashes, and respecting the noncommercial-research-only restriction used by the local validation. The CRAG mock-API result supports source/retrieval governance evidence under the configured utility, not generative LLM answer-quality validation. Commercial use requires separate license and legal review.

## Behaviorally Distinct Follow-Up

The follow-up suite `ragwarrant_behavioral_governance_primary_outcome_v1` reuses the sanitized frozen CRAG mock-API observations and compares genuinely different operating behaviors: one-endpoint low retrieval, two-endpoint expanded retrieval, variable-call adaptive routing, measured-cost selection, measured-latency selection, quality-only selection, constrained optimization, and Pareto frontier selection.

Result: `GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY`.

- Governed winner: `low_retrieval_single_endpoint`
- Quality-only winner: `optuna_tpe`
- Quality metric: `QUALITY_MEASURE_PROXY_PLUS_EVIDENCE`
- Quality noninferiority margin: 0.01
- Evidence class: `public_full_corpus_mock_api_validation_derived_frozen_observation`

This follow-up avoids relying only on a small weighted-utility delta by using a predeclared quality floor and measured cost/latency outcomes. It remains bounded: no raw CRAG text is included, no new live API collection is claimed, and no human/generative validation is claimed.

## Fresh Live CRAG Attempt

The fresh live CRAG phase adds `ragwarrant_fresh_live_crag_mock_api_behavioral_governance_v1`. In this execution environment, approved local CRAG data and the mock-API KG/runtime were restored, and a 50-example sanitized live sample ran. The result is `FRESH_CRAG_BLOCKED_QUALITY_MEASURE_PROXY_ONLY`: endpoint behavior, API calls, latency, and cost were measured, but the sample did not produce a usable answer/evidence quality signal. This is a blocked result, not a replication claim.

To run it in an approved environment, set `RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY=true`, `RAGWARRANT_CRAG_ROOT`, and `RAGWARRANT_CRAG_DATA`; verify the mock-API KG files are complete and readable; start the CRAG mock API; then run `scripts/run_fresh_live_crag_behavioral_governance.py`.

## CRAG Generative LLM Status

`ragwarrant_crag_generative_llm_validation_v1` now includes a publication-safe evaluator mapping that scores generated answers against CRAG answers/alternate answers locally and exports only hashes, counts, and metrics. The qwen3 repair disables Ollama thinking output for `qwen3:8b`; the larger bounded 12-example primary rerun produced 132 nonempty generated answers and active evaluator mapping. The primary CRAG result is `GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG`, but independent deterministic 12-example repeats at offsets 24, 36, and 60 returned `GEN_LLM_GOVERNANCE_INCONCLUSIVE_CRAG`. A second pinned local model, `gpt-oss:20b`, was run on the same offsets and produced `CRAG_GEN_LLM_COST_RESULT_INCONCLUSIVE_ACROSS_REPEATS`. A faster non-thinking instruct model, `llama3.2:3b`, repaired answer emission on four 16-example fixed-offset slices with 0 / 704 parse failures, but all four initial cost-endpoint slices remained `GEN_LLM_GOVERNANCE_INCONCLUSIVE_CRAG`. A predeclared unguarded latency-endpoint selector comparison then separated governed and quality-only winners on all four `llama3.2:3b` fixed-offset slices and consistently reduced latency/API calls, but only offset 24 met generated-quality noninferiority. The label-aware quality-risk guarded latency selector selected `quality_guarded_latency_adaptive_expansion`; it avoided quality-loss result classes on all four fixed offsets, but produced `CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS` because latency-reduction CIs crossed zero. The first learned deployable risk predictor selected `learned_quality_risk_latency_adaptive_expansion`; it reduced validation expansion rates on every offset and produced one latency-positive slice, but two confirmatory slices exceeded the generated-quality loss threshold. CRAG Generative Quality-Risk Guardrail v2 used pooled cross-offset validation, deployable-only retrieval features, held-out-offset testing, and strict quality-loss blocking. It returned `CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS`, so no latency-selector promotion is made. Raw CRAG question text, source documents, raw API responses, prompts, and generated answers are not committed.
