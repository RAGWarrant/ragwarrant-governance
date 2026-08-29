# AWS Zero-to-First-Run Runbook

This runbook describes how an operator can run the finite RAGWarrant governance job on AWS ECS Fargate or AWS Batch. It is a deployment guide only. It does not report live cloud validation, production readiness, official benchmarking, or platform certification.

## Prerequisites

- A published digest in `deploy/IMAGE_DIGEST`.
- AWS credentials configured outside this repository.
- An ECS cluster or AWS Batch queue created by the operator.
- Network egress to `ghcr.io`, or a private mirror of the same digest.
- A writable artifact destination selected by the operator.

## Preflight

```bash
deploy/load-image-reference.sh
python3 scripts/validate_publication_bundle.py
```

If `deploy/load-image-reference.sh` reports that no verified published digest is recorded, run the GHCR publish workflow first and merge the generated digest-record pull request.

## Deploy

### ECS Fargate

```bash
export RAGWARRANT_AWS_CLUSTER="<ecs-cluster-name>"
export RAGWARRANT_AWS_SUBNET="<subnet-id>"
export RAGWARRANT_AWS_SECURITY_GROUP="<security-group-id>"

bash deploy/aws/deploy-ecs-fargate.sh
bash deploy/aws/run-ecs-task.sh
```

### AWS Batch

```bash
export RAGWARRANT_AWS_BATCH_QUEUE="<batch-queue-name>"

aws batch register-job-definition --cli-input-json file://deploy/aws/batch-job-definition.json
bash deploy/aws/submit-batch-job.sh
```

## Run

Use `bash deploy/aws/run-ecs-task.sh` for ECS Fargate or
`bash deploy/aws/submit-batch-job.sh` for AWS Batch after the corresponding
definition is registered.

## Expected Outputs

The job should write:

- `promotion_decision.json`
- `run_manifest.json`
- `validation_report.json`
- `validation_report.md`
- sanitized public-mini artifacts

The public-mini job is expected to fail closed with a `BLOCK` decision unless a future config changes the result class through validated evidence.

## Troubleshooting

- Pending digest: run the publish workflow and update `deploy/IMAGE_DIGEST`.
- Package is not public: make the GHCR package public, configure a pull secret, or mirror the digest into an AWS registry.
- Missing outputs: check the selected artifact destination and task logs.
- Nonzero exit code `2`: config or mounted input issue.
- Nonzero exit code `3`: publication validator or governance gate failed.

## Rollback

Use the prior `deploy/IMAGE_DIGEST` record or the prior Git commit. Do not retag mutable images as a rollback mechanism.

## Claim Boundaries

Running this job does not establish production readiness, official cloud benchmarking, human validation, generative validation, or RAG Compass superiority.
