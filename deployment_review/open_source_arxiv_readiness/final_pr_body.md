## Summary

Adds the next RAGWarrant open-source and arXiv-readiness validation package.

This PR includes:

1. CRAG Quality-Risk Guardrail v2 fail-closed result.
2. Public mini reproduction path.
3. HotpotQA generative quality-signal audit metadata.
4. CRAG generated-answer evaluator mapping diagnostics.
5. External-evaluator input adapters.
6. Selector ablation matrix.
7. Local AIM hardware performance characterization.
8. Open-source/arXiv readiness synthesis.

## Scientific interpretation

This PR does not claim stable generative cost/latency superiority. The key finding is that RAGWarrant behaves as a governance and promotion-control framework: it preserves mixed and negative evidence, blocks unsafe promotion under held-out quality loss, and provides machine-checked claim boundaries.

## Results

- Guardrail v2: `CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS`
- Public mini reproduction: `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`
- HotpotQA quality-signal audit: `HOTPOTQA_GEN_LLM_QUALITY_SIGNAL_CONFIRMED`
- CRAG evaluator mapping: `CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE`
- External evaluator adapters: `EXTERNAL_EVALUATOR_ADAPTER_PROMOTION_DECISION_GENERATED`
- Selector ablation matrix: `SELECTOR_ABLATION_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS`
- AIM hardware characterization: `AIM_HARDWARE_CHARACTERIZATION_COMPLETED`
- Readiness synthesis: `OPEN_SOURCE_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES`

## Validation

- publication validator: passed
- pytest: `124 passed`
- make validate-publication: passed
- make test: `124 passed`
- compile: passed
- diff-check: passed
- raw text/prompt/generated-answer scan: passed after manual inspection
- secret scan: passed after manual inspection
- private path scan: passed after manual inspection
- large-file scan: no tracked public artifact over threshold

## Claim boundaries

This PR does not claim RAG Compass superiority, stable generative cost reduction, stable generative latency reduction, broad generative governance superiority, human validation, official platform benchmarking, production readiness, or hallucination elimination.

## Recommended next experiment

Prepare the arXiv systems/methods draft around RAGWarrant as an evidence-preserving RAG governance and promotion-control framework, while continuing targeted CRAG evaluator mapping and generative quality-risk experiments.
