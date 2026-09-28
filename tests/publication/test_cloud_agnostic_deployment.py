# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from ragwarrant.deployment_readiness import DEPLOYMENT_TARGETS, validate_deployment_readiness


ROOT = Path(__file__).resolve().parents[2]


def test_deployment_readiness_targets_cover_required_platforms() -> None:
    targets = {target for target, _ in DEPLOYMENT_TARGETS}
    assert {
        "local_docker",
        "docker_compose",
        "github_actions",
        "kubernetes_job",
        "kubernetes_cronjob",
        "azure_container_apps_job",
        "aws_ecs_fargate",
        "aws_batch",
        "gcp_cloud_run_job",
    }.issubset(targets)


def test_deployment_readiness_validator_writes_sanitized_outputs(tmp_path: Path) -> None:
    manifest = validate_deployment_readiness(ROOT, output_root=tmp_path)
    assert manifest["raw_data_committed"] is False
    assert manifest["secrets_committed"] is False
    assert (tmp_path / "promotion_decision.json").exists()
    assert (tmp_path / "deployment_target_matrix.csv").exists()
