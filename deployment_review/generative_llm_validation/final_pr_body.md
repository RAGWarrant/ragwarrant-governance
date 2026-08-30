## Summary

Adds RAGWarrant Generative LLM Validation v1. This validates policy-specific generated answers using a pinned generator where available, sanitized generated-answer metrics, and strict publication hygiene.

## Generator status

- Provider: `ollama`
- Model: `qwen3:8b`
- Local or hosted: local
- Raw answers committed: no
- Prompt text committed: no
- Secrets committed: no

## CRAG generative result

- Evidence class: `crag_generative_validation_sanitized_bounded_sample`
- Result class: superseded by v1.1 as `GEN_LLM_VALIDATION_BLOCKED_NO_USABLE_QUALITY_SIGNAL_CRAG`
- Generator: `ollama` / `qwen3:8b`
- Quality metric class: `GENERATED_QUALITY_CRAG_LOCAL_EVALUATOR`
- Governed winner: `static_default_policy`
- Quality-only winner: `adaptive_routing_on_insufficient_evidence`
- Constrained optimizer winner: `static_default_policy`
- Pareto frontier: `measured_latency_minimizer_at_quality_floor`, `static_default_policy`
- RAG Compass rank: 11
- Generated-quality delta: 0.0 [0.0, 0.0]
- Evidence-support delta: 0.0 [0.0, 0.0]
- Cost delta: -1.125 [-1.125, -1.125]
- Latency delta: about -119 ms
- API-call delta: -1.0 [-1.0, -1.0]

## HotpotQA generative result

- Evidence class: `hotpotqa_local_generative_validation_sanitized_bounded_sample`
- Result class: superseded by v1.1 as `GEN_LLM_GOVERNANCE_INCONCLUSIVE`
- Generator: `ollama` / `qwen3:8b`
- Quality metric class: `GENERATED_QUALITY_HOTPOTQA_ANSWER_LABELS_PLUS_SUPPORTING_FACTS`
- Governed winner: `rag_compass_optional`
- Quality-only winner: `expanded_retrieval_multi_context`
- Constrained optimizer winner: `rag_compass_optional`
- Pareto frontier: `adaptive_routing_on_insufficient_evidence`, `rag_compass_optional`
- RAG Compass rank: 2
- Generated-quality delta: 0.0 [0.0, 0.0]
- Answer-correctness delta: 0.0 [0.0, 0.0]
- Supporting-fact evidence delta: 0.0 [0.0, 0.0]
- Cost delta: -1.09255 [-1.0943, -1.0943]
- Latency delta: about -100 ms

## Synthesis

- Result class: superseded by v1.1 as `GEN_LLM_SYNTHESIS_MIXED`
- Interpretation: the v1.1 audit confirmed HotpotQA quality variation without governance improvement, while the larger bounded CRAG generative sample produced reduced measured cost at equivalent generated-answer quality.

## Validation

- publication validator: passed
- pytest: 51 passed
- make validate-publication: passed
- make test: 51 passed
- compile: passed
- raw prompt/generated-answer scan: passed with expected field-name/sanitizer/test references only
- secret scan: passed with expected scanner/config variable-name references only
- private path scan: passed
- large-file scan: passed for public tree

## Claim boundaries

This PR does not claim official platform benchmarking, human validation, production readiness, hallucination elimination, broad universal governance superiority, or RAG Compass superiority.
