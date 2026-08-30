# GCP Zero-to-First-Run Runbook

This runbook describes how an operator can run the finite RAGWarrant governance job as a Google Cloud Run job. It is a deployment guide only. It does not report live GCP validation, production readiness, official benchmarking, or platform certification.

## Prerequisites

- A published digest in `deploy/IMAGE_DIGEST`.
- GCP credentials configured outside this repository.
- A GCP project and region selected by the operator.
- Cloud Run Jobs enabled by the operator.
- Network egress to `ghcr.io`, or a private mirror of the same digest.

## Preflight

```bash
deploy/load-image-reference.sh
python3 scripts/validate_publication_bundle.py
```

If the image reference is pending, run the GHCR publish workflow first and update `deploy/IMAGE_DIGEST` from the workflow artifact.

## Deploy

```bash
export RAGWARRANT_GCP_REGION="<gcp-region>"

bash deploy/gcp/deploy-cloud-run-job.sh
```

## Run

```bash
export RAGWARRANT_GCP_REGION="<gcp-region>"

bash deploy/gcp/run-cloud-run-job.sh
```

## Expected Outputs

The job should emit a schema-valid `promotion_decision.json` plus sanitized run and validation reports. Configure Cloud Logging export or mounted artifact storage externally if outputs must be retained beyond the job.

## Troubleshooting

- Pending digest: run the publish workflow and update `deploy/IMAGE_DIGEST`.
- Registry pull failure: make the GHCR package public, configure credentials, or mirror the digest into a GCP registry.
- Missing artifacts: verify output capture and job logs.
- Exit code `2`: config or mounted input issue.
- Exit code `3`: publication validator or governance gate failed.

## Rollback

Rollback by restoring the previous `deploy/IMAGE_DIGEST` record or Git commit. Do not use mutable tags.

## Claim Boundaries

Running this job does not establish production readiness, official GCP benchmarking, human validation, generative validation, or RAG Compass superiority.

