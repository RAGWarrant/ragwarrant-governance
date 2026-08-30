# Docker Runtime Validation

RAGWarrant can run as a local containerized governance job. RAGWarrant is not the chatbot; it is the governance job that checks whether a proposed RAG policy is safe to promote, should be blocked, should be rejected, or remains inconclusive.

## What The Container Does

- starts a finite RAGWarrant job;
- loads a governance config;
- runs or imports sanitized policy metrics;
- writes audit artifacts under `/outputs`;
- emits `/outputs/promotion_decision.json`;
- validates claim boundaries;
- exits.

## What The Container Does Not Do

- it does not include raw CRAG or HotpotQA data;
- it does not include prompts or generated answers;
- it does not include cloud credentials;
- it does not perform live cloud deployment;
- it does not establish official platform benchmarking;
- it does not certify production operation.

## Local Docker Commands

```bash
docker build -t ragwarrant-governance:local .
mkdir -p docker_outputs
docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --pids-limit 256 \
  --memory 1g \
  --cpus 2 \
  -v "$(pwd)/docker_outputs:/outputs" \
  ragwarrant-governance:local run-governance-job --config configs/jobs/public_mini_governance_job.yaml --output-root /outputs --decision-out /outputs/promotion_decision.json
```

The smoke-test runner validates the same hardened runtime posture: no container network, read-only root filesystem, writable `/outputs` mount only, tmpfs `/tmp`, `no-new-privileges`, all Linux capabilities dropped, and bounded CPU, memory, and process counts.

## Docker Compose

```bash
mkdir -p docker_outputs
docker compose -f docker/compose.public-mini.yml up --build --abort-on-container-exit --exit-code-from ragwarrant-public-mini
```

## Podman

If Docker is unavailable and Podman is configured:

```bash
podman build -t ragwarrant-governance:local .
mkdir -p docker_outputs
podman run --rm -v "$(pwd)/docker_outputs:/outputs" ragwarrant-governance:local run-governance-job --config configs/jobs/public_mini_governance_job.yaml --output-root /outputs --decision-out /outputs/promotion_decision.json
```

## Mounts

- `/outputs`: required writable output directory.
- `/configs`: optional external config mount.
- `/inputs`: optional sanitized input mount.
- `/data`: optional approved local data mount for experiments that require external data.

Do not commit mounted raw datasets, prompts, generated answers, API responses, Docker caches, or credentials.

## Result Classes

- `DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI`: Docker built and ran the public-mini governance job.
- `CONTAINER_RUNTIME_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE`: a CLI exists but no usable daemon was available.
- `CONTAINER_RUNTIME_VALIDATION_SKIPPED_ENGINE_UNAVAILABLE`: no supported container engine was available.
- `CONTAINER_RUNTIME_VALIDATION_FAILED`: runtime validation was attempted and failed.

Static Docker validation can pass even when runtime validation is skipped. That supports deployment enablement, not live runtime proof.

## Troubleshooting Daemon Unavailable

Start Docker Desktop, Colima, or another local container engine, then rerun:

```bash
python3 scripts/diagnose_container_runtime.py --output-root artifacts/docker_hardening --force
python3 scripts/run_container_smoke_tests.py --config configs/experiments/ragwarrant_container_smoke_tests_v1.yaml --output-root artifacts/docker_hardening --force
```

Cloud templates can later use the same image in Azure, AWS, or GCP, but those are deployment examples unless an approved environment runs and preserves separate evidence.
