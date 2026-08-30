# Docker

RAGWarrant can run as a finite governance job in a container. The container starts, evaluates or imports sanitized RAG policy metrics, writes audit artifacts, emits `promotion_decision.json`, validates claim boundaries, and exits.

Default command:

```bash
docker build -t ragwarrant-governance:local .
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

The image does not include raw CRAG or HotpotQA datasets, local caches, credentials, prompts, or generated answers. Mount approved local data at `/data` only for local experiments that require it.

Docker runtime validation is local deployment validation, not cloud validation. Cloud templates are deployment examples, not official platform benchmarks. Production operation is not claimed unless separately validated.

The public-mini runtime path is intentionally hardened: no network, read-only root filesystem, `/tmp` as tmpfs, no new privileges, all Linux capabilities dropped, and bounded CPU/memory/process limits. `/outputs` remains writable because it is the only required runtime output mount.

Compose:

```bash
mkdir -p docker_outputs
docker compose -f docker/compose.public-mini.yml up --build --abort-on-container-exit --exit-code-from ragwarrant-public-mini
```

If Docker daemon access is unavailable, run the static fallback:

```bash
python3 scripts/validate_docker_static.py --output-root artifacts/docker_hardening --force
```
