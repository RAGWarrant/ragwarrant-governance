## Summary

Adds CRAG Generative Quality-Risk Guardrail v2, a conservative held-out-offset validation of deployable quality-risk gating for generative RAG policy selection.

This experiment tested whether RAGWarrant can reduce retrieval expansion, latency, or cost while preserving generated-answer quality across held-out CRAG generative validation offsets.

## Result

Result class:

`CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS`

The guardrail failed closed correctly. Although the predictor passed validation gates on all offsets and reduced expansion in places, held-out testing showed quality-loss risk that was not stable enough to support promotion.

## Key Outcomes

- Predictor validation gates passed: `4 / 4`
- Positive latency held-out results: `0 / 4`
- Held-out quality-loss blocking fired: `3 / 4`
- Conservative synthesis remains: `GEN_LLM_SYNTHESIS_MIXED`

## What Changed

This PR adds:

- `scripts/run_crag_quality_risk_guardrail_v2.py`
- `configs/experiments/ragwarrant_crag_generative_quality_risk_guardrail_v2.yaml`
- `artifacts/generative_llm_validation/crag_quality_risk_guardrail_v2/`
- `results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.*`

It also updates the synthesis, validator, tests, README/docs, paper scaffold, claim tables, run index, and evidence summary.

## Scientific Interpretation

This is not a positive governance win.

The experiment shows that deployable-only quality-risk prediction is not yet sufficient to safely reduce latency or cost across held-out CRAG generative offsets. RAGWarrant correctly blocks promotion when generated-answer quality loss appears under held-out evaluation.

This strengthens the governance story by demonstrating refusal discipline under harder generative validation.

## Validation

Local validation passed:

- `python3 scripts/validate_publication_bundle.py`
- `pytest -q tests/publication` -> `86 passed`
- `make validate-publication`
- `make test` -> `86 passed`
- `python3 -m compileall src scripts`
- `git diff --check`

Publication hygiene passed:

- No raw CRAG questions committed.
- No raw evidence committed.
- No raw prompts committed.
- No raw generated answers committed.
- No raw API responses committed.
- No secrets committed.
- No private paths committed.
- Large-file scan found only ignored `.local_data` cache files, not tracked public artifacts.

## Claim Boundaries

This PR does not claim:

- stable generative cost reduction;
- stable generative latency reduction;
- broad generative governance superiority;
- RAG Compass superiority;
- human validation;
- official platform benchmarking;
- production readiness;
- hallucination elimination.

## Recommended Next Experiment

The next step should be a more conservative risk model or rule family that prioritizes quality preservation over latency reduction, with held-out-offset quality-loss blocking retained as the primary promotion gate.
