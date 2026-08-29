# Final Rename Report

- Python package: `ragwarrant`
- CLI: `ragwarrant`
- Environment prefix: `RAGWARRANT_`
- Repository: `https://github.com/RAGWarrant/ragwarrant-governance`
- Legacy exceptions: 26831
- Unclassified old-name hits: 0

Verification gates:

- `python3 -m compileall src scripts`: passed
- `pytest -q tests/publication/test_cli_entrypoints.py`: 5 passed
- clean editable install: `ragwarrant` import/CLI passed; legacy `ragtune` import/CLI absent
- `ragwarrant run-public-mini --output-root /tmp/ragwarrant-clean-public-mini`: passed with `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`
- `python3 scripts/validate_docker_static.py`: `DOCKER_STATIC_VALIDATION_PASSED`
- `make validate-publication`: passed
- `make validate-deployment-readiness`: `DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES`
- `pytest -q tests/publication --tb=short`: 267 passed, 6 skipped
- `git diff --check`: passed
