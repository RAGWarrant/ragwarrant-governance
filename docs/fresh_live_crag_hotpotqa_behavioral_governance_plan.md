# Fresh Live CRAG + HotpotQA Behavioral Governance Plan

## Scientific Motivation

The prior behaviorally distinct result showed that RAGWarrant governance reduced measured operating cost at equivalent proxy-plus-evidence quality, but it was derived from sanitized frozen CRAG mock-API observations. This phase tests whether that result can move beyond frozen observations.

## Prior Frozen-Observation Limitation

Frozen observations are useful for audit and publication hygiene, but they do not prove that the same behavior holds under a fresh live mock-API collection or on another public corpus with stronger answer labels.

## Datasets

- CRAG fresh live mock-API collection, subject to noncommercial research-only use and approved local data access.
- HotpotQA alternate public corpus, preferred because it provides answer labels, multi-hop structure, bridge/comparison types, difficulty labels, and sentence-level supporting facts.

## Acquisition Plan

CRAG requires `RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY=true`, `RAGWARRANT_CRAG_ROOT`, and `RAGWARRANT_CRAG_DATA`. HotpotQA should be acquired locally through Hugging Face `datasets` or the official HotpotQA repository. Raw data stay outside Git.

## License And Redistribution Boundaries

CRAG raw data are not redistributed and remain noncommercial research-only. HotpotQA raw data are not committed. This repository publishes sanitized manifests, metrics, hashes, and aggregate summaries only.

## Candidate Policy Suite

The suite includes low retrieval, expanded retrieval, adaptive routing, measured-cost selection, measured-latency selection, quality-only selection, constrained optimization, Pareto selection, governed selection, static default, and optional RAG Compass secondary comparison.

## Behavioral Distinction Requirements

Behavior must be measured through endpoint/context set distance, API-call counts, context count, estimated context tokens, source count, latency, measured cost, abstention rate, answer-quality delta, and supporting-fact recall for HotpotQA.

## Quality Measurement Plan

CRAG uses proxy-plus-evidence plus local evaluator correctness if available. HotpotQA uses exact match, normalized F1, supporting-fact title recall, supporting-fact sentence recall, evidence efficiency, and abstention correctness.

## Cost And Latency Measurement Plan

CRAG uses measured API calls and latency. HotpotQA uses measured retrieval latency, context-count cost, and estimated context tokens.

## Statistical Plan

Compute paired query bootstrap, grouped bootstraps where actual group labels exist, win/tie/loss, probability of noninferiority, probability of cost reduction, probability of latency reduction, rank stability, and Pareto frontier stability. Mark unavailable grouped bootstraps as unavailable rather than duplicating query bootstrap values.

## Promotion Rules

Primary success requires equivalent quality under a 0.01 noninferiority margin with lower measured cost or latency, or higher quality under a fixed budget.

## Repeat / Robustness Plan

Use deterministic splits and repeat over CRAG strata or HotpotQA type/difficulty strata when data are available. Frozen-observation resplits are weaker and cannot establish replication by themselves.

## Publication Hygiene

No raw CRAG query text, HotpotQA questions, source documents, context paragraphs, supporting-fact text, or raw API responses may be committed.

## Claim Boundaries

No RAG Compass superiority, human validation, generative validation, official benchmark status, production readiness, or broad governance superiority is claimed unless directly supported.

## Expected Artifacts

- `artifacts/fresh_live_crag_behavioral_governance/`
- `artifacts/hotpotqa_behavioral_governance/`
- `results/multi_dataset_behavioral_governance/`
