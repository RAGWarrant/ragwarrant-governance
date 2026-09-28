# Open Core Foundation Preflight

Review date: 2026-09-28

## Repository State

- Public repository: `https://github.com/RAGWarrant/ragwarrant-governance`
- Target base branch: `main`
- Feature branch: `open-core-commercialization-foundation`
- Starting main SHA: `b0b3ea388f39c007f6760b2943aadd49184fdeeb`
- Origin main SHA at branch creation: `b0b3ea388f39c007f6760b2943aadd49184fdeeb`
- Repository owner from GitHub API: `RAGWarrant`
- Visibility: `public`
- Default branch: `main`

## Public Release Tags

- `V1_VALID_ZERO_POWER_BASELINE`
- `ragwarrant-focus1-freeze-v1-c771afc`
- `v0.1.0-rc1`

## Existing Licensing and Governance Files

- `LICENSE`: Apache License 2.0 with neutral `RAGWarrant contributors` attribution.
- `NOTICE`: absent before this branch.
- `CODEOWNERS`: absent before this branch.
- `GOVERNANCE.md`: absent before this branch.
- `TRADEMARKS.md`: absent before this branch.
- `COMMERCIAL.md`: absent before this branch.
- `SUPPORT.md`: absent before this branch.

## Open Pull Requests

- `#27 Rename governance project to RAGWarrant`, head branch `holistic-ragwarrant-rename`.

Research PRs were not merged or disturbed as part of this task.

## Active Workflows

- CI: `.github/workflows/ci.yml`
- k8s-kind-validation: `.github/workflows/k8s-kind-validation.yml`
- Publication Check: `.github/workflows/publication-check.yml`
- Publish Container: `.github/workflows/publish-container.yml`
- Research FULL future-beacon seal: `.github/workflows/research-full-seal.yml`
- storage-staging-validation: `.github/workflows/storage-staging-validation.yml`

## Branch Protection and Rulesets

- Branch protection API for `main`: not found through accessible API.
- Repository rulesets API: empty list.
- Result: `BRANCH_PROTECTION_SETUP_PENDING_ADMIN_ACTION`

## Baseline Validation

Initial preflight found an inherited brand-consistency failure in current manuscript artifacts after the latest `main` fast-forward:

- `pytest -q tests/publication`: failed with 5 active former-name occurrences.
- `scripts/validate_brand_consistency.py`: failed with 5 active former-name occurrences.

This branch repairs those manuscript references. After the repair:

- `pytest -q tests/publication`: passed, `274 passed, 6 skipped`.
- `scripts/validate_brand_consistency.py`: passed with zero active former-name occurrences.
- `python3 scripts/validate_publication_bundle.py`: passed.
- `python3 -m compileall src scripts`: passed.
- `git diff --check`: passed.

## LFS Attribute Note

The fast-forward from `main` produced a local LFS cleanliness warning for `paper/RAGWarrant_arXiv_source.zip`: the file is tracked under a broad `*.zip` LFS attribute but committed upstream as a normal binary blob. This branch adds a narrow `.gitattributes` override for that file so clean clones do not show a false dirty state.
