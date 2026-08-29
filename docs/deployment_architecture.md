# Deployment Architecture

RAGWarrant runs as a finite job:

```text
configs + sanitized inputs -> ragwarrant CLI -> audit artifacts + promotion_decision.json
```

The same entrypoint is intended for local terminal runs, Docker, Docker Compose, Kubernetes Jobs and CronJobs, Azure Container Apps Jobs, AWS ECS/Fargate tasks, AWS Batch jobs, Google Cloud Run Jobs, and GitHub Actions.

## Container Contract

```text
Input mount: /inputs
Config mount: /configs
Output mount: /outputs
Optional local data mount: /data
Runtime command: ragwarrant run-governance-job --config /configs/job.yaml --output-root /outputs --decision-out /outputs/promotion_decision.json
```

Exit behavior:

- `0`: job completed and validation passed.
- nonzero: missing inputs, failed validation, unsupported claims, raw-data leak, secret-like pattern, or runtime failure.

## Artifact Flow

The job always writes a local `promotion_decision.json` before attempting any optional artifact-sink upload. Cloud storage adapters are optional and fail closed when SDKs or credentials are absent.

## Boundary

The templates in this repository are deployment examples and portability checks. They are not official Azure, AWS, GCP, Kubernetes, or GitHub performance benchmarks.

Container runtime validation is local Docker/Podman validation only. It validates the public-mini governance job when an engine is available and records a skip when the daemon or engine is unavailable.
