# RAGWarrant Brand Completion Preflight

- Repository path: `<local workspace>/ragwarrant-governance`
- Starting branch: `holistic-ragwarrant-content-rename`
- Starting main commit: `85b319c6cbb923578ab9ac3c58a20e9e42cd284f`
- Current HEAD: `85b319c6cbb923578ab9ac3c58a20e9e42cd284f`
- Remote: `https://github.com/RAGWarrant/ragwarrant-governance.git`
- Immutable tag target: `ff529005bf7d00a0c3f79ba991563f3923d63205`
- Immutable commit type: `commit`

## Active Starting Surfaces

- Python distribution: `rag-tuning-governance`
- Import package: `ragtune`
- CLI entrypoint: `ragtune = ragtune.cli:main`
- Docker images: `ragtune-governance:local, ragtune-governance:ci`
- GHCR paths: `ghcr.io/aim-ragtune/rag-tuning-governance`
- Repository URLs: `https://github.com/AIM-RAGTune/rag-tuning-governance, https://github.com/AIM-RAGTune/rag-tuning-governance-public`

## Inventory Counts

- former_name_text_inventory: 10246
- former_name_path_inventory: 175
- former_name_tracked_paths: 438
- office_document_inventory: 2
- pdf_inventory: 6
- figure_inventory: 6

## Baseline Results

- validate_publication_bundle: failed: external git remote configured in publication bundle
- pytest_publication: 1 failed, 264 passed, 6 skipped
- make_test: failed through publication validator: 1 failed, 264 passed, 6 skipped
- make_validate_publication: failed: external git remote configured in publication bundle
- compileall_src_scripts: passed
- git_diff_check: passed
- make_reproduce_public_mini: public mini generated PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED; make target failed at old publication validator
- verify_run: VERIFY_RUN_PASSED
- semantic_baseline_path: /tmp/ragwarrant-pre-rename-semantic-baseline.json
- verify_run_output_path: /tmp/ragwarrant-pre-rename-verify-run.txt
