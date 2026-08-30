# Historical Validation Summary

RAGWarrant is a governance-first RAG policy promotion and validation framework. The historical validation record shows an evidence arc from synthetic simulations and refusal discipline through public end-to-end development, public confirmatory noninferiority, CRAG full corpus-backed acquisition, and CRAG mock-API governance superiority.

RAGWarrant governance is the main evidence-backed contribution. It evaluates candidate policies and optimizers under declared quality, cost, latency, regression, safety, provenance, reproducibility, and statistical constraints.

RAG Compass is a candidate optimizer inside RAGWarrant. Its legacy machine-readable ID is `ragtune_no_fork`. Historical evidence does not support RAG Compass optimizer superiority. In the strongest CRAG mock-API validation run, RAG Compass ranked 5th.

Negative, blocked, refused, and inconclusive results are intentionally preserved in `results/historical/`. They reduce cherry-picking and explain why the current claim boundary is narrow.

The strongest current result is CRAG mock-API governance superiority under a source/retrieval governance evaluation path: governed selection chose `top_k_low` over quality-only `greedy_regression_aware_search` on held-out confirmatory rows under the configured utility.

A later behaviorally distinct follow-up over the sanitized frozen CRAG mock-API observations produced `GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY`: governed selection chose `low_retrieval_single_endpoint` while quality-only selected `optuna_tpe` under a proxy-plus-evidence quality metric. This strengthens the operating-constraint interpretation but remains frozen-observation evidence, not independent human/generative validation.

The fresh live CRAG + HotpotQA phase adds the next validation harness. Fresh CRAG now has a restored local data/mock-API environment and a sanitized 50-example live sample, but remains blocked as `FRESH_CRAG_BLOCKED_QUALITY_MEASURE_PROXY_ONLY` because the sample did not produce a usable answer/evidence quality signal. HotpotQA ran from local cached public data with sanitized outputs and returned `HOTPOTQA_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS`, meaning operating cost improved but quality noninferiority was not established. This negative/mixed status is preserved to avoid upgrading frozen-observation evidence into a replication claim.

Generative LLM Validation v1.1 adds bounded local HotpotQA and CRAG quality-signal audits, producing `GEN_LLM_SYNTHESIS_MIXED`. HotpotQA quality scoring became nonconstant but did not support a governance improvement; after qwen3 answer emission and evaluator mapping repair, the larger bounded CRAG primary slice produced `GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG`, but three independent deterministic CRAG repeats did not reproduce the cost result. A second pinned local generator, Ollama `gpt-oss:20b`, produced usable generated-quality signals on the same four offsets but no positive cost-result slices. A faster non-thinking instruct model, Ollama `llama3.2:3b`, repaired answer emission on four slightly larger 16-example CRAG slices with 0 / 704 parse failures. A follow-up unguarded latency-endpoint selector comparison separated governed and quality-only winners and consistently reduced latency/API calls, but only one of four fixed-offset slices preserved generated-quality noninferiority. A label-aware quality-risk guardrail avoided quality-loss result classes, but the guarded latency stability result was inconclusive. A learned deployable quality-risk predictor reduced validation expansion rates, but confirmatory quality protection did not persist on two fixed-offset slices; the learned-predictor result is `CRAG_GEN_LLM_LEARNED_RISK_PREDICTOR_LATENCY_MIXED_CONFIRMATORY_QUALITY_LOSS`. Guardrail v2 pooled validation evidence across offsets and used held-out-offset testing with deployable-only features; it blocked promotion as `CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS`.

Unsupported areas remain: RAG Compass superiority, broad generative LLM governance validation beyond the current mixed bounded local CRAG/HotpotQA evidence, human-evaluation validation, official external-platform benchmarking, production readiness, broad governance superiority across many public datasets, and legacy hardware/quantum-advantage.

No raw datasets, raw CRAG query wording, raw source documents, raw API responses, or private paths are included in the historical ledger.
## Open-Source And arXiv Readiness Update

The latest readiness package preserves the historical negative and mixed results while adding a deterministic public mini reproduction, external evaluator adapter demo, selector ablation matrix, CRAG evaluator-mapping diagnostics, and sanitized AIM hardware characterization. The package supports presenting RAGWarrant as a governance and promotion-control framework, not as a universal optimizer.

## Cloud-Agnostic Deployment Update

The deployment-hardening pass adds a CLI job contract, Docker support, Docker Compose and cloud deployment examples, storage-sink abstractions, promotion-decision schemas, and deployment-readiness validation. This strengthens RAGWarrant as open-source governance infrastructure. It does not change the scientific evidence ladder and does not claim live cloud benchmarking or production operation.
