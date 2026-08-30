# Fresh Live CRAG Unblock Preflight

## Repository State

- Starting commit: `07b4ee089d7cec6468092b0038f23e422f6b6c28`
- Branch: `fresh-live-crag-unblock-validation`
- Remote: `https://github.com/RAGWarrant/ragwarrant-governance.git`
- Working tree before CRAG unblock changes: clean at branch creation; CRAG unblock artifacts and source hardening were then modified on this branch.

## Baseline Validation

- `python3 scripts/validate_publication_bundle.py`: passed
- `pytest -q tests/publication`: 34 passed
- `make validate-publication`: passed
- `make test`: 34 passed
- `python3 -m compileall src scripts`: passed

## Existing Evidence State

- Existing fresh CRAG status before this unblock attempt: `FRESH_CRAG_BLOCKED_NO_APPROVED_DATA`
- Existing HotpotQA status before this unblock attempt: `HOTPOTQA_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS`

## Hygiene Scan Interpretation

- Raw data/query/API-response scan: passed with expected references to redacted field names, scanner definitions, and documentation.
- Secret scan: passed with expected scanner-pattern references only.
- Private path scan: passed after excluding gitignored local data caches.
- Overclaim scan: passed with expected unsupported-claim statements only.

## CRAG Environment Attempt

- Approval env var: present during acquisition and suite runs.
- CRAG root configured: true.
- CRAG data configured: true.
- Local evaluator available: true.
- Mock API path available: true.
- Mock API runtime available: false.
- Blocking reason: `open_kg_unreadable:OSError`.

No raw CRAG data, raw query wording, source documents, or mock-API responses were copied into the public repository.
