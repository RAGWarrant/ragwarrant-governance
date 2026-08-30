## Summary

This PR consolidates the public survivor repository posture by removing vestigial legacy quantum-simulation code, vendoring the small hash utility RAGWarrant still needed, classifying private-source differences through reviewed file-level inventory, and updating canonical public repository references.

The public repository history remains immutable. No private git history was merged, rebased, cherry-picked, pulled, or imported.

## Hard-invariant confirmation

- `main` was not rewritten.
- `ff529005bf7d00a0c3f79ba991563f3923d63205` remains reachable and unchanged.
- `v0.1.0-rc1` remains reachable and unchanged.
- No private git history was imported.
- No raw CRAG/HotpotQA text, prompts, generated answers, API responses, secrets, tokens, private paths, hostnames, or IP addresses were committed.

## Task A - Legacy Simulation Excision

- Removed the legacy simulation source tree, related configs, and direct legacy-only tests.
- Vendored `stable_hash` into `src/ragwarrant/utils/hashing.py`.
- Updated RAGWarrant imports that depended on the removed utility package.
- Regression verified exact `stable_hash` outputs on representative inputs.

## Task B - Private Repository Consolidation

- Private source repo inspected through file-level inventory only.
- Private source commit: `367f01aeb34f2e45c425bb20561cccda7f57540b`.
- Candidate paths reviewed/classified: 1370.
- Imported paths: 0.
- Excluded paths: 1370.
- See `deployment_review/repo_consolidation_square_excision/SKIP_REPORT.md` for sanitized display paths, hashes, and reasons.

## Canonical Repository URL Cleanup

- Public canonical repository: `https://github.com/RAGWarrant/ragwarrant-governance`.
- Updated citation and stale deployment-review URL references as needed.

## Verification Gates

1. Clean install: passed after approved network access for build dependencies.
2. `make test`: 224 passed.
3. `make reproduce-public-mini`: `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`.
4. `make validate-publication`: passed.
5. Removed-package grep: no content hits.
6. Full branch diff security/privacy sweep: passed with documented allowed hits.
7. Deployment readiness: `DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES`.
8. Compile: passed.
9. Diff check: passed.
10. Docker validation: build, validate, and container public-mini all passed.

## Before/After Test Counts

- Before: 219 passed, 3 CLI subprocess import failures.
- After: 224 passed.

## Remaining Allowed Legacy-Name References

Tracked content contains no removed package token. Filename exceptions are limited to the requested deployment-review directory and report filenames for this task.

## Claim Boundaries

This PR does not claim:

- RAG Compass superiority
- stable generative cost/latency superiority
- broad generative governance superiority
- human validation
- official platform benchmarking
- production readiness
- hallucination elimination
