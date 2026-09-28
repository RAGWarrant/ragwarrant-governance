# RAGWarrant Governance

Status: `PUBLIC_CORE_GOVERNANCE_FOUNDATION`

## Mission

RAGWarrant Community/Core provides an Apache-2.0, vendor-neutral governance engine for deciding whether measured evidence justifies promotion, refusal, blocking, or inconclusive handling of RAG policy changes.

## Apache Core

The public core remains Apache-2.0. This governance document does not narrow rights already granted under Apache-2.0 and does not change scientific findings, evidence classes, claim boundaries, historical artifacts, or release tags.

## Roles

- Maintainers review public-core changes, preserve scientific claim boundaries, and enforce repository hygiene.
- CODEOWNERS identify files requiring designated review.
- Release managers prepare public releases, verify reproducible artifacts, and preserve published tags.
- Security responders handle vulnerability intake and coordinate fixes.
- Contributors submit changes under Apache-2.0 and, once activated, the approved CLA process.

## Distinct Legal and Governance Concepts

- Copyright ownership is a legal question and remains pending human IP review.
- Maintainership is repository-operational authority.
- Trademark ownership remains pending human trademark review.
- Commercial licensing authority remains pending human IP review.

Do not collapse these concepts into one claim.

## Merge Authority

Changes to `main` should occur through pull requests. Maintainers should require passing CI, publication validation, brand validation, license/header validation, and open-core boundary validation before merge.

## Release Process

Public releases should use semantic versioning where practical, publish Apache-2.0 source artifacts, include public SBOM or dependency metadata when available, and preserve release tags against deletion or force-update.

## Vulnerability Handling

Security reports should avoid public issue disclosure until triaged. Commercial SLA terms are established only in an applicable order form or support agreement and are not promised by this public-core governance document.

## Commercial and Core Separation

Enterprise-only software, if later authorized, must depend on the Apache core rather than duplicating it wherever practical. Public-core security fixes must not be withheld merely to create enterprise value.

## Historical Evidence Preservation

Historical evidence, negative results, blocked results, and inconclusive results are preserved to avoid cherry-picking. Commercial positioning must not relabel noncommercial research evidence as production or enterprise validation.
