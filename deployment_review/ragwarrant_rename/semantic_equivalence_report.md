# Semantic Equivalence Report

Status: verified for rename-relevant gates.

Expected differences are namespace, repository URL, package name, CLI name, GHCR image namespace, and version metadata changes. No scientific claim is changed by the rename.

Verification evidence:

- `python3 -m compileall src scripts`: passed
- `pytest -q tests/publication/test_cli_entrypoints.py`: 5 passed
- clean editable install imported `ragwarrant`: passed
- clean editable install did not expose `ragtune`: passed
- clean editable install exposed `ragwarrant --help`: passed
- `ragwarrant run-public-mini --output-root /tmp/ragwarrant-clean-public-mini`: passed
- public-mini result class: `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`
- `python3 scripts/validate_docker_static.py`: `DOCKER_STATIC_VALIDATION_PASSED`
- `make validate-publication`: passed
- `make validate-deployment-readiness`: `DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES`
- `pytest -q tests/publication --tb=short`: 267 passed, 6 skipped
- `git diff --check`: passed
