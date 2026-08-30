## Summary

This PR adds the above-the-fold product-positioning guard, adds the planned v0.2 roadmap without implementing it, makes five surgical manuscript edits, creates a faithful arXiv-compatible LaTeX version, recreates all figures as vectors, and adds abstract-length and clean-build checks.

## README Changes

```markdown
## What RAGWarrant is — and is not

RAGWarrant is a promotion-governance controller that decides whether measured evidence justifies promoting a change to a RAG policy. It is not a hyperparameter tuner, an optimizer, or an evaluation library. It sits behind existing tuning and evaluation tools and adjudicates their outputs through explicit quality, risk, cost, latency, and evidence gates.
```

Planned v0.2 items added without implementation:

- Native evidence-ingestion adapters for LangChain, LlamaIndex, and Haystack.
- Direct ingestion of evaluator-platform exports, replacing the current synthetic-shaped adapter demonstrations with real exported evidence.
- PyPI publication and installation through a versioned package release.
- Group-sequential and adaptive noninferiority-margin designs with prespecified spending functions.
- A completed blinded human-adjudication study, prioritized as the highest-leverage next validation for healthcare and other high-consequence settings.

These items are planned work, not capabilities or evidence claimed by the current release.

## Manuscript Change Report

- Section 6.2 conjunction correction.
- Reference [7] colon correction.
- Canonical code-link update in front matter and software reference.
- Evaluator-layer-noise sentence.
- Sequential-design future-work sentence.

The Word change-control report verifies no unexplained manuscript content changes.

## LaTeX Package

- Main source: `paper/main.tex`.
- Bibliography: `paper/refs.bib`.
- Vector figures: `paper/figures/figure_01_governance_loop.pdf` through `paper/figures/figure_06_selector_stress_test.pdf`, with source companions and `paper/figures/figure_data.json`.
- Clean-build result: passed with TeX layout warnings using the documented Tectonic fallback.
- Page count: 20.
- Abstract character count: 1278/1920.
- Undefined-reference count: 0.
- Missing-citation count: 0.
- Raster-figure count: 0.

## Validation

- Publication validator: passed.
- `pytest -q tests/publication`: 265 passed, 6 skipped.
- `make test`: 265 passed, 6 skipped.
- `make validate-publication`: passed.
- `python3 -m compileall src scripts`: passed.
- `git diff --check`: passed.
- Word change-control report: passed.
- Secret/privacy scan: passed with expected scanner/config/test references only.
- Protected-path diff: passed; claim/status tables unchanged.

## Claim Boundaries

No benchmark-superiority claim was added.
No RAG Compass superiority claim was added.
No human-validation claim was added.
No production-readiness claim was added.
No platform-native evidence claim was added.
No multimodal or RBAC scope was added.

## Council Review Rule

Review critiques were considered only when they cited a current file path, commit SHA, or test name.

## Human-Only Submission Steps

- [ ] arXiv abstract confirmation at upload.
- [ ] endorsement if required.
- [ ] Fairview COI disclosure before the final submission timestamp.
- [ ] arXiv submission.
- [ ] external preprint Code-link update.
