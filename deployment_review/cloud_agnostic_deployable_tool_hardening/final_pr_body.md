## Summary

Adds cloud-agnostic deployment hardening for RAGWarrant as a finite open-source governance and promotion-control job.

This PR adds a CLI job contract, Docker image contract, Docker Compose example, Kubernetes Job/CronJob examples, Azure Container Apps Job example, AWS ECS/Fargate and Batch examples, Google Cloud Run Job example, GitHub Actions examples, storage-sink abstractions, promotion-decision schemas, deployment-readiness validation, and publication tests.

## Product contract

- RAGWarrant is the governance engine, not the chatbot or model.
- Default job: `ragwarrant run-governance-job --config /configs/job.yaml --output-root /outputs --decision-out /outputs/promotion_decision.json`
- Machine-readable decision: `promotion_decision.json`
- Decisions: `PROMOTE`, `BLOCK`, `REJECT`, `INCONCLUSIVE`, `ERROR`
- Default public mini job requires no raw datasets, generator, cloud credentials, or private data.

## Deployment targets

- Docker
- Docker Compose
- GitHub Actions
- Kubernetes Job
- Kubernetes CronJob
- Azure Container Apps Job
- AWS ECS/Fargate
- AWS Batch
- Google Cloud Run Job

## Validation

- publication validator: pass
- pytest: 141 passed
- make validate-publication: pass
- make test: 141 passed
- compile: pass
- deployment-readiness validator: pass
- git diff check: pass
- tracked large-file scan: pass
- private path scan: pass
- raw text scan: pass with expected sanitized field names, hashes, false flags, tests, and code references only
- secret scan: pass with expected environment-variable names and scanner definitions only

## Docker

- Docker CLI: available
- Docker daemon: unavailable from this session
- Docker build/run: not completed because the daemon socket was not reachable
- Readiness artifact: `DOCKER_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE`

## Claim boundaries

This PR does not claim live cloud validation, official platform benchmarking, human validation, production operation, hallucination elimination, broad universal governance superiority, stable generative cost/latency superiority, or RAG Compass superiority.
