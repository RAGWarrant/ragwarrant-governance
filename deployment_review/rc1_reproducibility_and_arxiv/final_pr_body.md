## Summary

Adds the RC1 reproducibility and arXiv readiness package for RAGWarrant.

This PR strengthens RAGWarrant as an open-source RAG governance and promotion-control framework by adding fresh-clone reproduction, release-candidate preparation, CRAG evaluator mapping diagnostics, HotpotQA quality-signal audit, selector ablation stress testing, artifact integrity verification, external evaluator adapter demos, AIM hardware characterization, and arXiv paper scaffolding.

## Key results

- Fresh clone reproducibility: `FRESH_CLONE_REPRODUCTION_PASSED_GIT_CLONE`
- Docker runtime/static validation: `DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI`
- Release candidate: `RELEASE_CANDIDATE_READY`
- CRAG evaluator mapping v2: `CRAG_EVALUATOR_MAPPING_V2_ACTIVE_NONCONSTANT_SIGNAL`
- HotpotQA quality-signal audit v2: `HOTPOTQA_GEN_QUALITY_AUDIT_V2_CONFIRMED_NONCONSTANT_SIGNAL`
- Selector ablation stress v2: `SELECTOR_ABLATION_STRESS_V2_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS`
- Verify-run: `VERIFY_RUN_PASSED`
- External evaluator adapters v2: `EXTERNAL_EVALUATOR_ADAPTER_V2_PROMOTION_DECISION_GENERATED`
- AIM hardware matrix: `AIM_HARDWARE_MATRIX_COMPLETED`
- arXiv readiness synthesis: `RC1_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES`

## Scientific interpretation

This PR does not attempt to force a positive governance result. It improves reproducibility, auditability, deployment readiness, external evaluator interoperability, and paper readiness.

Fail-closed, mixed, blocked, and inconclusive results are preserved.

## Validation

- publication validator: passed
- deployment readiness validator: `DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES`
- pytest: `222 passed`
- make validate-publication: passed
- make test: `222 passed`
- compile: passed
- diff-check: passed
- large-file scan: passed; only ignored `.local_data` cache exceeded threshold
- raw text scan: passed with expected sanitized field names and scanner references
- secret scan: passed with expected env-var names and scanner patterns only
- private-path scan: passed with expected negative-test strings only
- overclaim scan: passed with explicit unsupported-claim statements only

## Claims now supported

- RAGWarrant has a public mini reproduction path.
- RAGWarrant has hardened Docker/container validation.
- RAGWarrant can emit auditable promotion decisions.
- RAGWarrant can verify run artifact integrity.
- RAGWarrant can consume external evaluator-style metric exports.
- RAGWarrant has selector ablation stress-test tooling.
- RAGWarrant has AIM local hardware characterization.
- RAGWarrant has an arXiv-ready systems/methods draft scaffold.

## Claims still unsupported

- RAG Compass superiority.
- Stable generative cost/latency superiority.
- Broad generative governance superiority.
- Human validation.
- Official platform benchmarking.
- Production readiness.
- Hallucination elimination.

## Release candidate

- RC version: `v0.1.0-rc1`
- Tag created: no, pending merge to `main`
- Tag pushed: no, pending merge to `main`

## Publication hygiene

No raw CRAG questions, raw HotpotQA text, raw evidence, raw prompts, raw generated answers, raw API responses, secrets, private paths, Docker caches, local dataset caches, or large generated artifacts are committed.

## Recommended next step

Use the RC1 artifacts to prepare and refine the arXiv systems/methods paper, then run targeted CRAG evaluator mapping and larger HotpotQA audits only where the paper has specific gaps.
