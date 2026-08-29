# Repository Map

This map points publication readers to the major repository areas without changing any scientific claims.

- `.github/`: GitHub Actions for CI, publication validation, container publication, kind execution validation, and storage-emulator validation.
- `artifacts/`: Sanitized selected artifacts, manifests, and small reproduction outputs. Raw datasets, raw prompts, raw generated answers, and raw API responses are excluded.
- `configs/`: Experiment, job, optimizer, and policy-space configurations, including the public-mini governance job.
- `data/`: Dataset availability and licensing notes. Raw CRAG and HotpotQA data are not redistributed here.
- `deploy/`: Docker, Kubernetes, AWS, Azure, GCP, and digest-resolution deployment examples.
- `deployment_review/`: Sanitized review records, publication checks, and repository-consolidation reports.
- `docker/`: Docker Compose support for local public-mini execution.
- `docs/`: Claim boundaries, dataset acquisition, governance design notes, deployment contracts, artifact integrity, and validation summaries.
- `docs/design/`: Design and criteria notes that are useful background but not manuscript content.
- `examples/`: Small example inputs or usage material where present.
- `notebooks/`: Notebook area for sanitized, publication-safe notebooks where present.
- `paper/`: LaTeX paper scaffold, figures, tables, and manuscript-adjacent material.
- `paper/preprints/`: Versioned preprint exports moved out of the repository root without editing manuscript content.
- `reproduction/`: Reproduction instructions and Docker-oriented notes.
- `results/`: Processed summary tables, evidence summaries, and historical evidence ledgers.
- `scenarios/`: Scenario fixtures or examples where present.
- `schemas/`: Machine-readable schemas for promotion decisions, run manifests, deployment readiness, and artifact manifests.
- `scripts/`: Reproduction, validation, deployment-readiness, container, storage-emulator, and digest-resolution scripts.
- `src/`: RAGWarrant source code.
- `tests/`: Publication, reproducibility, deployment, storage, and validator tests.

Key root files:

- `README.md`: Main orientation, quickstart, current evidence posture, and claim boundaries.
- `LICENSE`: Apache-2.0 code license.
- `CITATION.cff`: Citation metadata with canonical repository URL.
- `Dockerfile`: Hardened finite-job runtime image.
- `Makefile`: Reproduction and validation shortcuts.
- `pyproject.toml`: Python package metadata and optional dependency groups.
- `requirements-runtime.lock`: Hashed runtime dependency lock.
- `requirements-dev.lock`: Hashed development/publication-test dependency lock.
- `requirements-storage-emulators.lock`: Hashed integration dependency lock for emulator-backed object-storage validation.
