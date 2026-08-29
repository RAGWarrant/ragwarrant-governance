from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_assets_exist_and_exclude_local_data() -> None:
    assert (ROOT / "Dockerfile").exists()
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for token in [".local_data", ".env", "*.pem", "*.key", "artifacts/raw"]:
        assert token in dockerignore


def test_cloud_deployment_templates_exist() -> None:
    required = [
        "deploy/kubernetes/ragwarrant-job.yaml",
        "deploy/kubernetes/ragwarrant-cronjob.yaml",
        "deploy/azure/container-apps-job.bicep",
        "deploy/aws/ecs-fargate-task.json",
        "deploy/aws/batch-job-definition.json",
        "deploy/gcp/cloud-run-job.yaml",
        "deploy/github-actions/validate-docker.yml",
    ]
    for rel in required:
        assert (ROOT / rel).exists(), rel


def test_deployment_readiness_manifest_machine_readable() -> None:
    path = ROOT / "artifacts/deployment_readiness/deployment_readiness_manifest.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["result_class"] in {
        "DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES",
        "DEPLOYMENT_READINESS_BLOCKED_PUBLICATION_HYGIENE",
    }
    assert payload["official_platform_benchmarking_claimed"] is False
    assert payload["production_readiness_claimed"] is False


def test_deployment_docs_do_not_claim_official_platform_benchmarking() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in [
            ROOT / "docs/cloud_agnostic_deployment.md",
            ROOT / "docs/deployment_architecture.md",
            ROOT / "docs/operator_workflow.md",
        ]
    )
    assert "official platform benchmarking completed" not in text
    assert "validated in production" not in text
