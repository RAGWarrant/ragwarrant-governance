from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _deploy_files() -> list[Path]:
    return sorted(p for p in (ROOT / "deploy").rglob("*") if p.is_file())


def test_deploy_templates_do_not_use_latest_or_example_registries() -> None:
    offenders: list[str] = []
    for path in _deploy_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "ubuntu-latest" in text:
            continue
        for token in ("ghcr.io/example", "ragwarrant-governance:latest", "ragwarrant-governance:latest", "dkr.ecr", "us-docker.pkg.dev"):
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}:{token}")
    assert offenders == []


def test_digest_helper_fails_closed_when_digest_pending(tmp_path: Path) -> None:
    pending_digest = tmp_path / "IMAGE_DIGEST"
    pending_digest.write_text(
        "IMAGE=ghcr.io/aim-ragwarrant/ragwarrant-governance\n"
        "REFERENCE=PENDING_FIRST_WORKFLOW_RUN\n"
        "DIGEST=PENDING_FIRST_WORKFLOW_RUN\n"
        "PLATFORMS=linux/amd64,linux/arm64\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["RAGWARRANT_IMAGE_DIGEST_FILE"] = str(pending_digest)
    result = subprocess.run(
        ["bash", "deploy/load-image-reference.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "No verified published image digest is recorded" in result.stderr


def test_cloud_scripts_preflight_with_digest_helper() -> None:
    scripts = [
        "deploy/aws/deploy-ecs-fargate.sh",
        "deploy/aws/run-ecs-task.sh",
        "deploy/aws/submit-batch-job.sh",
        "deploy/azure/deploy-aca-job.sh",
        "deploy/azure/run-aca-job.sh",
        "deploy/gcp/deploy-cloud-run-job.sh",
        "deploy/gcp/run-cloud-run-job.sh",
    ]
    for script in scripts:
        text = (ROOT / script).read_text(encoding="utf-8")
        assert "load-image-reference.sh" in text


def test_kubernetes_manifests_are_non_root_and_read_only() -> None:
    for name in ("ragwarrant-job.yaml", "ragwarrant-cronjob.yaml"):
        text = (ROOT / "deploy" / "kubernetes" / name).read_text(encoding="utf-8")
        assert "runAsNonRoot: true" in text
        assert "runAsUser: 10001" in text
        assert "readOnlyRootFilesystem: true" in text
        assert "allowPrivilegeEscalation: false" in text
        assert "mountPath: /inputs" in text
        assert "mountPath: /outputs" in text


def test_k8s_kind_validator_reports_fallback_without_tools(tmp_path: Path) -> None:
    env = os.environ.copy()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env["PATH"] = str(empty_bin)
    env["PYTHON"] = sys.executable
    result = subprocess.run(
        ["/bin/bash", "scripts/validate_k8s_kind.sh", str(tmp_path / "report")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "FALLBACK_KUBECTL_UNAVAILABLE" in (tmp_path / "report" / "k8s_kind_validation_report.json").read_text(encoding="utf-8")


def test_k8s_kind_validator_explicit_full_refuses_silent_downgrade(tmp_path: Path) -> None:
    env = os.environ.copy()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env["PATH"] = str(empty_bin)
    env["PYTHON"] = sys.executable
    result = subprocess.run(
        ["/bin/bash", "scripts/validate_k8s_kind.sh", "--full", str(tmp_path / "report")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    report = json.loads((tmp_path / "report" / "k8s_kind_validation_report.json").read_text(encoding="utf-8"))
    assert report["result_class"] == "K8S_KIND_FULL_VALIDATION_FAILED"
    assert report["scheduler_execution_performed"] is False


def test_k8s_kind_validator_has_full_and_dry_run_modes() -> None:
    text = (ROOT / "scripts" / "validate_k8s_kind.sh").read_text(encoding="utf-8")
    assert "--full" in text
    assert "--dry-run" in text
    assert "RAGWARRANT_K8S_VALIDATION_MODE" in text
    assert "K8S_KIND_STATIC_DRY_RUN_PASSED" in text
    assert "K8S_KIND_EXECUTION_PASSED" in text


def test_k8s_kind_validator_checks_security_and_decision_result() -> None:
    text = (ROOT / "scripts" / "validate_k8s_kind.sh").read_text(encoding="utf-8")
    for token in (
        "runAsUser",
        "runAsNonRoot",
        "readOnlyRootFilesystem",
        "allowPrivilegeEscalation",
        "capabilitiesDropAll",
        "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED",
        "promotion_decision.json",
    ):
        assert token in text


def test_k8s_kind_validator_uses_cleanup_trap() -> None:
    text = (ROOT / "scripts" / "validate_k8s_kind.sh").read_text(encoding="utf-8")
    assert "trap cleanup EXIT INT TERM" in text
    assert "kind delete cluster" in text


def test_kind_validation_overlay_uses_public_mini_config_and_local_image() -> None:
    text = (ROOT / "deploy" / "kubernetes-kind-validation" / "kustomization.yaml").read_text(encoding="utf-8")
    assert "public_mini_governance_job.yaml" in text
    assert "ragwarrant-governance" in text
    assert "kind-validation" in text
    assert (ROOT / "deploy" / "kubernetes-kind-validation" / "public_mini_governance_job.yaml").read_text(encoding="utf-8") == (
        ROOT / "configs" / "jobs" / "public_mini_governance_job.yaml"
    ).read_text(encoding="utf-8")


def test_k8s_kind_workflow_invokes_shared_script_and_verifies_checksums() -> None:
    text = (ROOT / ".github" / "workflows" / "k8s-kind-validation.yml").read_text(encoding="utf-8")
    assert "scripts/validate_k8s_kind.sh --full" in text
    assert "KIND_VERSION: v" in text
    assert "KUBECTL_VERSION: v" in text
    assert "sha256sum -c" in text
    assert "kind-linux-amd64.sha256sum" in text
    assert "kubectl.sha256" in text
    assert "K8S_KIND_EXECUTION_PASSED" in text
