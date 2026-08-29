# Azure Zero-to-First-Run Runbook

This runbook describes how an operator can run the finite RAGWarrant governance job as an Azure Container Apps job. It is a deployment guide only. It does not report live Azure validation, production readiness, official benchmarking, or platform certification.

## Prerequisites

- A published digest in `deploy/IMAGE_DIGEST`.
- Azure credentials configured outside this repository.
- An Azure resource group selected by the operator.
- A Container Apps managed environment or permission to create one.
- Network egress to `ghcr.io`, or a private mirror of the same digest.

## Preflight

```bash
deploy/load-image-reference.sh
python3 scripts/validate_publication_bundle.py
```

If the image reference is pending, run the GHCR publish workflow first and update `deploy/IMAGE_DIGEST` from the workflow artifact.

## Deploy

```bash
export RAGWARRANT_AZURE_RESOURCE_GROUP="<resource-group-name>"

bash deploy/azure/deploy-aca-job.sh
```

## Run

```bash
export RAGWARRANT_AZURE_RESOURCE_GROUP="<resource-group-name>"
export RAGWARRANT_AZURE_JOB_NAME="ragwarrant-governance-job"

bash deploy/azure/run-aca-job.sh
```

## Expected Outputs

The job should emit a schema-valid `promotion_decision.json` plus sanitized run and validation reports. Configure persistent storage or log export externally if artifacts must survive beyond the job execution window.

## Troubleshooting

- Pending digest: run the publish workflow and update `deploy/IMAGE_DIGEST`.
- Registry pull failure: make the GHCR package public, configure registry credentials, or mirror the digest into an Azure registry.
- Missing artifacts: verify external storage wiring and job logs.
- Exit code `2`: config or mounted input issue.
- Exit code `3`: publication validator or governance gate failed.

## Rollback

Rollback by restoring the previous `deploy/IMAGE_DIGEST` record or Git commit. Do not use mutable tags.

## Claim Boundaries

Running this job does not establish production readiness, official Azure benchmarking, human validation, generative validation, or RAG Compass superiority.

