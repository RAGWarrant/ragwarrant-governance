# Quickstart

Run the publication-safe mini reproduction:

```bash
make reproduce-public-mini
```

The mini reproduction uses a tiny synthetic dataset generated in code. It does not require CRAG, HotpotQA, a local generator, hosted credentials, or cloud services.

For the full publication bundle checks:

```bash
make validate-publication
make test
```

Run the deployment-friendly governance job:

```bash
python3 -m ragwarrant.cli run-governance-job \
  --config configs/jobs/public_mini_governance_job.yaml \
  --output-root artifacts/public_mini_governance_job \
  --decision-out artifacts/public_mini_governance_job/promotion_decision.json
```

Validate deployment-readiness assets:

```bash
make validate-deployment-readiness
```

Build and run the public mini job in Docker when a local Docker daemon is available:

```bash
make docker-build
make docker-run-public-mini
```
