# Historical Reproducibility Summary

RAGWarrant validation emphasized append-only artifacts, strict provenance checks, no-overwrite discipline, leakage checks, and reproducibility gates.

Known summarized test milestones:

- Fixture/smoke phase: full repo 242 passed, 1 skipped.
- Phase 2 audit: full repo 268 passed, 1 skipped, 2 warnings.
- Row-level/public dev: full repo 280 passed.
- Public dev v2: full repo 297 passed, 1 skipped, 2 warnings.
- Governance confirmatory attempt: full repo 310 passed, 1 skipped, 2 warnings.
- Fresh public data phase: full repo 329 passed, 1 skipped, 2 warnings.
- Valid confirmatory run: full repo 336 passed, 1 skipped, 2 warnings.
- Governance expansion: full repo 352 passed, 1 skipped, 2 warnings.
- Later dataset/multi-corpus: full repo 373 passed, 1 skipped, 2 warnings.
- RAGBench enablement: full repo 395 passed, 1 skipped, 2 warnings.
- CRAG phase: full repo 439 passed, 1 skipped, 2 warnings.
- Later CRAG mock API phase: full repo 493 passed, 1 skipped, 4 warnings.
- Latest packaged source status: full repo 530 passed, 1 skipped, 4 warnings.

CRAG-specific reproducibility included raw hash matching, zero cross-split leakage, streaming normalization, confirmatory-row checks, and policy variation checks. Docker decision reproduction supported the parent CRAG mock-API decision, with numeric caveats documented elsewhere in this repository.

Source for counts: summarized_project_record unless a referenced local artifact provides the exact count.
