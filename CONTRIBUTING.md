# Contributing

RAGWarrant Community/Core is Apache-2.0. Contributions should preserve append-only evidence handling, dataset-license boundaries, and explicit claim limits.

Before opening a change:

1. Run `make validate-publication`.
2. Run the relevant tests.
3. Do not add raw licensed datasets, credentials, model weights, or private annotation keys.
4. Label simulations, diagnostic evidence, context-retrieval evidence, and corpus-backed evidence separately.

## Contributor Authority

Contributors must have authority to submit their work. Employer-owned contributions require employer authorization. Do not submit proprietary code, licensed datasets outside their permitted terms, secrets, private legal agreements, customer information, raw CRAG data, raw HotpotQA data, raw prompts, or raw generated answers.

## Licensing

Accepted public-core contributions are intended to be distributed under Apache-2.0 unless a file clearly states otherwise. Contributors retain copyright unless a separate written agreement states otherwise.

## CLA Status

`CLA.md` is currently a draft requiring legal review before activation. Once a CLA mechanism is approved and activated, outside contributions will require a completed CLA before merge. A new CLA is prospective unless existing contributors separately agree; do not infer that historical contributors are CLA-covered.

## Enterprise-Code Boundary

No outside contribution may be copied from the Apache core into proprietary enterprise code merely because it was submitted under Apache-2.0. Proprietary reuse must have a documented rights basis such as company authorship, assignment, suitable CLA, or separate commercial license.
