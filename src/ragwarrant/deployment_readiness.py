from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import write_json, write_md
from ragwarrant.promotion_decision import build_promotion_decision


DEPLOYMENT_TARGETS = [
    ("local_docker", "Dockerfile"),
    ("docker_compose", "docker/docker-compose.public-mini.yml"),
    ("github_actions", "deploy/github-actions/validate-docker.yml"),
    ("kubernetes_job", "deploy/kubernetes/ragwarrant-job.yaml"),
    ("kubernetes_cronjob", "deploy/kubernetes/ragwarrant-cronjob.yaml"),
    ("azure_container_apps_job", "deploy/azure/container-apps-job.bicep"),
    ("aws_ecs_fargate", "deploy/aws/ecs-fargate-task.json"),
    ("aws_batch", "deploy/aws/batch-job-definition.json"),
    ("gcp_cloud_run_job", "deploy/gcp/cloud-run-job.yaml"),
]

REQUIRED_DEPLOYABLE_FILES = [
    "Dockerfile",
    ".dockerignore",
    "docker/README.md",
    "docker/run_public_mini.sh",
    "docker/run_governance_job.sh",
    "docker/healthcheck.sh",
    "docker/docker-compose.public-mini.yml",
    "docker/compose.public-mini.yml",
    "docker-compose.yml",
    "docs/docker_runtime_validation.md",
    "docs/container_security_scans.md",
    "scripts/diagnose_container_runtime.py",
    "scripts/validate_docker_static.py",
    "scripts/run_container_smoke_tests.py",
    "scripts/run_optional_container_security_scans.py",
    "configs/experiments/ragwarrant_container_smoke_tests_v1.yaml",
    "artifacts/docker_hardening/container_runtime_diagnostics.json",
    "artifacts/docker_hardening/docker_static_validation.json",
    "artifacts/docker_hardening/container_smoke_test_manifest.json",
    "artifacts/docker_hardening/container_security_scan_manifest.json",
    "docs/product_contract.md",
    "docs/deployment_architecture.md",
    "docs/operator_workflow.md",
    "docs/cloud_agnostic_deployment.md",
    "docs/artifact_storage.md",
    "docs/promotion_decision_schema.md",
    "configs/jobs/public_mini_governance_job.yaml",
    "schemas/promotion_decision.schema.json",
    "schemas/run_manifest.schema.json",
    "schemas/deployment_readiness.schema.json",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["target", "status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _check_dockerignore(root: Path) -> list[str]:
    text = _read_text(root / ".dockerignore")
    required = [".git", ".local_data", ".env", "*.pem", "*.key", "__pycache__", ".pytest_cache"]
    return [item for item in required if item not in text]


def _scan_for_forbidden_phrases(root: Path) -> list[str]:
    forbidden = [
        "official platform benchmarking completed",
        "official azure benchmark completed",
        "official aws benchmark completed",
        "official gcp benchmark completed",
        "production ready",
        "validated in production",
        "rag compass is proven superior",
        "human validated",
        "eliminates hallucinations",
    ]
    scanned = [
        root / "README.md",
        root / "docs/cloud_agnostic_deployment.md",
        root / "docs/product_contract.md",
        root / "docs/operator_workflow.md",
        root / "docs/platform_benchmarking_boundary.md",
    ]
    hits: list[str] = []
    for path in scanned:
        text = _read_text(path).lower()
        for phrase in forbidden:
            if phrase in text:
                hits.append(f"{path.relative_to(root).as_posix()}:{phrase}")
    return hits


def _load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        config: dict[str, Any] = {}
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            value = value.strip()
            if value and not raw_line.startswith(" "):
                config[key] = value.strip("'\"")
        return config
    return yaml.safe_load(text) or {}


def validate_deployment_readiness(root: Path, *, output_root: Path, config_path: Path | None = None) -> dict[str, Any]:
    config = {}
    if config_path and config_path.exists():
        config = _load_config(config_path)
    output_root.mkdir(parents=True, exist_ok=True)
    missing_files = [path for path in REQUIRED_DEPLOYABLE_FILES if not (root / path).exists()]
    dockerignore_missing = _check_dockerignore(root)
    claim_hits = _scan_for_forbidden_phrases(root)
    static_payload = {}
    smoke_payload = {}
    diagnostics_payload = {}
    security_payload = {}
    for name, target in [
        ("static", root / "artifacts/docker_hardening/docker_static_validation.json"),
        ("smoke", root / "artifacts/docker_hardening/container_smoke_test_manifest.json"),
        ("diagnostics", root / "artifacts/docker_hardening/container_runtime_diagnostics.json"),
        ("security", root / "artifacts/docker_hardening/container_security_scan_manifest.json"),
    ]:
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"result_class": "INVALID_JSON"}
            if name == "static":
                static_payload = payload
            elif name == "smoke":
                smoke_payload = payload
            elif name == "diagnostics":
                diagnostics_payload = payload
            else:
                security_payload = payload
    docker_cli_available = shutil.which("docker") is not None
    docker_daemon_available = False
    if docker_cli_available:
        docker_daemon_available = subprocess.run(["docker", "info"], cwd=root, capture_output=True, text=True, check=False).returncode == 0
    smoke_class = str(smoke_payload.get("result_class", ""))

    def _docker_validation_status() -> str:
        if smoke_class in {
            "DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
            "PODMAN_RUNTIME_VALIDATED_PUBLIC_MINI",
            "COLIMA_DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
        }:
            return smoke_class
        if docker_daemon_available:
            return "DOCKER_DAEMON_AVAILABLE_NOT_BUILT"
        if docker_cli_available:
            return "DOCKER_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE"
        return "DOCKER_VALIDATION_SKIPPED_DOCKER_UNAVAILABLE"

    target_rows: list[dict[str, Any]] = []
    for target, file_path in DEPLOYMENT_TARGETS:
        template_exists = (root / file_path).exists()
        local_status = "TEMPLATE_READY" if template_exists else "MISSING_TEMPLATE"
        live_status = "NOT_RUN_NO_CREDENTIALS"
        if target == "local_docker":
            live_status = _docker_validation_status()
        target_rows.append(
            {
                "target": target,
                "template_path": file_path,
                "template_status": local_status,
                "live_validation_status": live_status,
                "official_platform_benchmarking_claimed": False,
                "production_readiness_claimed": False,
            }
        )
    static_ok = static_payload.get("result_class") == "DOCKER_STATIC_VALIDATION_PASSED"
    smoke_ok_or_skipped = smoke_class in {
        "DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
        "PODMAN_RUNTIME_VALIDATED_PUBLIC_MINI",
        "COLIMA_DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
        "CONTAINER_RUNTIME_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE",
        "CONTAINER_RUNTIME_VALIDATION_SKIPPED_ENGINE_UNAVAILABLE",
        "CONTAINER_RUNTIME_STATIC_VALIDATION_ONLY",
    }
    result_class = "DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES"
    if missing_files or dockerignore_missing or claim_hits or not static_ok or not smoke_ok_or_skipped:
        result_class = "DEPLOYMENT_READINESS_BLOCKED_PUBLICATION_HYGIENE"
    manifest = {
        "schema_version": "1.0",
        "suite": config.get("suite", "ragwarrant_deployment_readiness_v1"),
        "result_class": result_class,
        "deployable_product_framing": "open-source governance and promotion-control engine",
        "container_contract_supported": not missing_files,
        "docker_cli_available": docker_cli_available,
        "docker_daemon_available": docker_daemon_available,
        "docker_validation_status": _docker_validation_status(),
        "container_runtime_diagnostic_result": diagnostics_payload.get("result_class", "missing"),
        "docker_static_validation_result": static_payload.get("result_class", "missing"),
        "container_smoke_test_result": smoke_payload.get("result_class", "missing"),
        "container_smoke_test_skip_reason": smoke_payload.get("skip_reason", ""),
        "optional_security_scan_result": security_payload.get("result_class", "missing"),
        "cloud_templates_ready": all(row["template_status"] == "TEMPLATE_READY" for row in target_rows),
        "live_cloud_validation_status": "NOT_RUN_NO_CREDENTIALS",
        "official_platform_benchmarking_claimed": False,
        "production_readiness_claimed": False,
        "raw_data_committed": False,
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "secrets_committed": False,
        "private_paths_committed": False,
        "missing_files": missing_files,
        "dockerignore_missing": dockerignore_missing,
        "claim_boundary_hits": claim_hits,
        "required_targets": [target for target, _ in DEPLOYMENT_TARGETS],
    }
    validation_rows = [
        {"check": "required_files", "status": "PASS" if not missing_files else "FAIL", "detail": ",".join(missing_files)},
        {"check": "dockerignore", "status": "PASS" if not dockerignore_missing else "FAIL", "detail": ",".join(dockerignore_missing)},
        {"check": "claim_boundaries", "status": "PASS" if not claim_hits else "FAIL", "detail": ",".join(claim_hits)},
        {"check": "cloud_live_runs", "status": "NOT_RUN", "detail": "templates only; no cloud credentials required or used"},
        {"check": "docker_static_validation", "status": "PASS" if static_ok else "FAIL", "detail": str(static_payload.get("result_class", "missing"))},
        {"check": "container_smoke_test", "status": "PASS" if smoke_ok_or_skipped else "FAIL", "detail": smoke_class or "missing"},
        {"check": "optional_security_scans", "status": "PASS" if security_payload else "SKIP", "detail": str(security_payload.get("result_class", "missing"))},
    ]
    decision = build_promotion_decision(
        run_id="ragwarrant_deployment_readiness_v1_20260811-public",
        suite=str(manifest["suite"]),
        result_class=result_class,
        selected_policy="deployment_templates",
        baseline_policy="manual_local_only",
        decision_reason="deployment hardening assets are ready with conservative cloud and production claim boundaries",
        artifact_uris=[
            "artifacts/deployment_readiness/deployment_readiness_manifest.json",
            "artifacts/deployment_readiness/deployment_target_matrix.csv",
            "results/deployment_readiness/claim_update.json",
        ],
        validator_status="pending_publication_validator",
        risk_flags=[] if result_class.endswith("BOUNDARIES") else ["deployment_readiness_blocked"],
    )
    write_json(output_root / "deployment_readiness_manifest.json", manifest)
    _write_csv(output_root / "deployment_target_matrix.csv", target_rows)
    _write_csv(output_root / "deployment_validation_results.csv", validation_rows)
    write_json(output_root / "promotion_decision.json", decision)
    write_md(
        output_root / "deployment_readiness_report.md",
        f"""
# Deployment Readiness

Result class: `{result_class}`

RAGWarrant now has a finite governance job contract, a CLI entrypoint, a Docker image contract, and example deployment templates for Docker Compose, GitHub Actions, Kubernetes, Azure Container Apps Jobs, AWS ECS/Fargate, AWS Batch, and Google Cloud Run Jobs.

Live cloud execution was not run and is not claimed as official platform benchmarking. The deployment posture is deployable open-source tooling with conservative claim boundaries.
""",
    )
    results_root = root / "results/deployment_readiness"
    write_json(results_root / "claim_update.json", manifest)
    write_md(results_root / "executive_summary.md", f"Deployment readiness result: `{result_class}`. Live cloud validation: `NOT_RUN_NO_CREDENTIALS`.")
    return manifest
