# Fresh Live CRAG + HotpotQA Preflight

- Starting commit: `03d5b93b5efc75bf94967ff1eac7f42bbdf6720a`
- Branch: `fresh-live-crag-hotpotqa-behavioral-governance`
- Remote: `https://github.com/RAGWarrant/ragwarrant-governance.git`
- Initial working tree: clean

## Baseline Validation

- `python3 scripts/validate_publication_bundle.py`: passed
- `pytest`: 16 passed
- `make validate-publication`: passed
- `make test`: 16 passed
- `python3 -m compileall src scripts`: passed

## Hygiene Scans

Raw-text, secret, private-path, and overclaim scans were run. Findings were expected references in validators, tests, prior sanitization reports, and explicit unsupported-claim documentation. No private paths were found and no secret values were found.

## Dataset Availability

Fresh CRAG could not run because `RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY`, `RAGWARRANT_CRAG_ROOT`, and `RAGWARRANT_CRAG_DATA` were not configured. HotpotQA could not run because the `datasets` package was unavailable and no local HotpotQA raw data were found.

## Decision

Proceed with implementation of the fresh/live and HotpotQA harnesses, run them, and preserve honest blocked results without upgrading the prior frozen-observation claim.
