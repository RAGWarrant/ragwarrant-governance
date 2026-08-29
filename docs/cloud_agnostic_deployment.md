# Cloud-Agnostic Deployment

RAGWarrant is packaged as a cloud-agnostic governance job. The repository includes templates for:

- local Docker
- Docker Compose
- GitHub Actions
- Kubernetes Job
- Kubernetes CronJob
- Azure Container Apps Job
- AWS ECS/Fargate task
- AWS Batch job
- Google Cloud Run Job

Each template runs the same finite command:

```bash
ragwarrant run-governance-job --config /configs/job.yaml --output-root /outputs --decision-out /outputs/promotion_decision.json
```

Cloud-specific templates are examples for operator adaptation. They intentionally use placeholders for image names, storage buckets, registries, service accounts, identities, and regions. No cloud credentials are committed, and live cloud execution is not claimed by this repository.

The deployment-readiness validator checks that examples are present and publication-safe. It marks live cloud runs as `NOT_RUN_NO_CREDENTIALS` unless operator-provided evidence exists.

Docker runtime hardening adds container-engine diagnostics, static Docker validation, and a public-mini smoke-test runner. If the local daemon is unavailable, the smoke-test runner records an explicit skip while preserving static validation.
