## Summary

Hardens the local Docker/container runtime path for the public RAGWarrant repository. This adds safe runtime diagnostics, static Docker validation, a public-mini container smoke-test runner, optional security-scan reporting, Docker Compose documentation, and deployment-readiness integration.

Docker Desktop was started locally and the daemon became readable from the validation shell. The PR records a completed public-mini Docker runtime validation after hardening the runtime posture and repairing the image copy/output contract needed for in-container publication validation.

## Runtime diagnostics

- Runtime diagnostic result: `CONTAINER_RUNTIME_DOCKER_READY`
- Docker CLI present: yes
- Docker daemon available: yes
- Docker Compose plugin available: yes
- Legacy `docker-compose` available: yes
- Buildx available: yes
- Podman ready: no
- Colima ready: no

## Docker static validation

- Result class: `DOCKER_STATIC_VALIDATION_PASSED`
- Checks passed: 29 / 29
- Dockerfile: hardened with container contract, non-root runtime, `/outputs` support, and healthcheck
- Dockerfile hardening: OCI labels, fixed non-root UID, disabled pip cache, explicit stop signal
- `.dockerignore`: hardened for local data, env files, secrets, caches, model/data binaries, and raw artifact patterns
- Compose path: `docker/compose.public-mini.yml` plus root `docker-compose.yml`
- Runtime hardening: no network, read-only root filesystem, tmpfs `/tmp`, no-new-privileges, all Linux capabilities dropped, process/memory/CPU limits
- Helper scripts/docs/tests: added or updated

## Container smoke test

- Result class: `DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI`
- Skip reason: none
- Docker build: passed
- `ragwarrant --help` in container: passed
- `ragwarrant validate-bundle` in container: passed
- Public-mini governance job in container: passed
- Compose public-mini: passed
- Hardened runtime flags: passed

## Optional security scans

- Result class: `CONTAINER_SECURITY_SCANS_PARTIAL`
- Docker Scout plugin: available, not run
- Critical findings: 0
- Scanner absence or non-execution is recorded, not treated as a hard failure.

## Deployment readiness

- Result class: `DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES`
- Live cloud execution: not run, no credentials
- Official platform benchmarking claimed: no
- Production readiness claimed: no

## Validation

- publication validator: passed
- pytest: `175 passed`
- make validate-publication: passed
- make test: `175 passed`
- compile: passed
- git diff check: passed
- tracked large-file scan: passed
- raw data/generated-answer scan: passed with expected sanitized field names and scanner references
- secret scan: passed with expected env-var names and scanner patterns only
- private path scan: passed with expected negative-test string only

## Claim boundaries

This PR does not claim live cloud validation, official platform benchmarking, production readiness, production operation, human validation, hallucination elimination, RAG Compass superiority, or stable generative cost/latency superiority.
