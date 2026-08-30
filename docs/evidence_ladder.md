# Evidence Ladder

The RAGWarrant validation program separates evidence by strength and claim boundary.

## Level 0 — Simulated / Synthetic Exploration

Synthetic and simulation-only results exercise mechanisms, controls, refusal behavior, and candidate ideas. They cannot establish external RAG performance.

## Level 1 — Engineering Smoke And Fixture Validation

Fixture, smoke, and implementation tests validate code paths and guardrails. They are necessary but not performance evidence.

## Level 2 — External-Transfer Development

External-transfer runs can produce candidate signals across imported datasets or scenarios. They remain development evidence unless frozen confirmatory designs are satisfied.

## Level 3 — Public End-To-End Development

Public end-to-end development runs evaluate policies on public data but may still be exploratory, non-confirmatory, or limited by context-only evidence classes.

## Level 4 — Public Confirmatory Noninferiority

Frozen held-out public confirmatory runs can support noninferiority when governance or optimizer choices match or avoid regressions, but do not necessarily show superiority.

## Level 5 — Multi-Corpus Mixed Evidence

Multi-corpus evidence improves breadth but must be stratified by evidence class. Context-retrieval evidence must not be relabeled as full corpus-backed evidence.

## Level 6 — Beneficial Natural Governance Divergence

Governance reaches this level when it changes a natural public promotion decision and evidence supports the governed choice as beneficial under the declared utility. RAGWarrant governance has reached Level 6 in a bounded CRAG mock-API source/retrieval governance setting.

The behaviorally distinct follow-up strengthens this level by reframing the strongest CRAG mock-API evidence around a predeclared quality noninferiority margin and measured operating outcomes. It does not move the program to Level 7 because it uses frozen observations and a proxy-plus-evidence quality metric rather than independent human, generative, or official platform validation.

## Level 7 — Docker-Reproduced And Human/Generative/Platform Validated Evidence

This level would require stronger independent reproduction and validation layers, including human evaluation, pinned generative LLM paths, and official platform integrations where claimed.

## Current Position

- RAGWarrant governance: Level 6 in a bounded CRAG mock-API source/retrieval governance setting.
- RAGWarrant governance has not reached Level 7.
- Fresh live CRAG replication remains blocked in the current public-repository execution environment. HotpotQA alternate-corpus validation ran with sanitized answer-label/supporting-fact metrics and returned `HOTPOTQA_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS`, a negative/mixed result rather than a Level 7 replication.
- Generative LLM Validation v1.1 adds bounded local HotpotQA and CRAG quality-signal audits with sanitized metrics. The primary CRAG generative slice with Ollama `qwen3:8b` supports cost reduction at equivalent generated-answer quality, but three independent deterministic CRAG repeats did not reproduce it. Ollama `gpt-oss:20b` produced usable generated-quality signals on the same four offsets but no positive cost-result slices. Ollama `llama3.2:3b` repaired answer emission on larger fixed-offset slices with 0 / 704 parse failures. A predeclared unguarded latency-endpoint selector comparison with `llama3.2:3b` separated governed and quality-only winners, but only one of four slices met generated-quality noninferiority. A label-aware quality-risk guarded latency selector avoided quality-loss result classes, but remained `CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS`. A learned deployable risk predictor reduced validation expansion rates, but confirmatory quality protection did not persist. Guardrail v2 pooled validation evidence across offsets and tested held-out offsets, then failed closed as `CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS`. The latest stability comparison is `CRAG_GEN_LLM_LATENCY_RESULT_MIXED_ACROSS_REPEATS`. HotpotQA remains inconclusive; the synthesis is mixed and does not move the program to Level 7.
- RAG Compass has not reached optimizer-superiority support.
- Human, official platform, production, broad-generalization, and hardware/quantum claims remain unsupported.
## Open-Source Readiness Layer

The current open-source readiness layer adds a public mini reproduction, external evaluator input adapters, selector ablations, CRAG evaluator-mapping diagnostics, and local AIM hardware characterization. This strengthens reproducibility and tooling maturity without changing the conservative generative synthesis, which remains mixed.

## Deployment Readiness Layer

The deployment-readiness layer adds a CLI, container contract, Docker and Docker Compose support, cloud example templates, artifact storage abstractions, machine-readable promotion decisions, and validator checks. It strengthens operational portability of the governance engine but does not move scientific evidence to a higher validation level by itself.
