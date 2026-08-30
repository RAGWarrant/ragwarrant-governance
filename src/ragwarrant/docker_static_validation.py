from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import write_json, write_md


STATIC_RESULT_CLASSES = {
    "DOCKER_STATIC_VALIDATION_PASSED",
    "DOCKER_STATIC_VALIDATION_PARTIAL",
    "DOCKER_STATIC_VALIDATION_FAILED",
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "detail"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_docker_static(root: Path, *, output_root: Path) -> dict[str, Any]:
    dockerfile = root / "Dockerfile"
    dockerignore = root / ".dockerignore"
    makefile = root / "Makefile"
    docker_text = dockerfile.read_text(encoding="utf-8") if dockerfile.exists() else ""
    ignore_text = dockerignore.read_text(encoding="utf-8") if dockerignore.exists() else ""
    make_text = makefile.read_text(encoding="utf-8") if makefile.exists() else ""
    compose_text = (root / "docker/compose.public-mini.yml").read_text(encoding="utf-8") if (root / "docker/compose.public-mini.yml").exists() else ""
    checks = [
        ("dockerfile_exists", dockerfile.exists(), "Dockerfile"),
        ("dockerfile_has_entrypoint_or_cmd", "ENTRYPOINT" in docker_text or "CMD" in docker_text, "ENTRYPOINT or CMD"),
        ("dockerfile_has_oci_labels", "org.opencontainers.image.title" in docker_text, "OCI labels"),
        ("dockerfile_sets_container_env", "RAGWARRANT_CONTAINER=1" in docker_text, "RAGWARRANT_CONTAINER=1"),
        ("dockerfile_disables_pip_cache", "PIP_NO_CACHE_DIR=1" in docker_text, "PIP_NO_CACHE_DIR=1"),
        ("dockerfile_supports_outputs", "/outputs" in docker_text, "/outputs"),
        ("dockerfile_fixed_non_root_uid", "--uid 10001" in docker_text and re.search(r"^USER\s+\w+", docker_text, re.M) is not None, "fixed non-root user"),
        ("dockerfile_has_stopsignal", "STOPSIGNAL SIGTERM" in docker_text, "STOPSIGNAL"),
        ("dockerfile_no_local_data_copy", ".local_data" not in docker_text, ".local_data absent"),
        ("dockerfile_no_git_copy", "COPY . " not in docker_text and not re.search(r"\.git(?:/|\s|$)", docker_text), "no broad copy"),
        ("dockerfile_copies_gitattributes", ".gitattributes" in docker_text, ".gitattributes"),
        ("dockerfile_copies_docker_assets", "Dockerfile" in docker_text and ".dockerignore" in docker_text and "docker-compose.yml" in docker_text and "COPY docker ./docker" in docker_text, "Docker assets"),
        ("dockerfile_copies_deploy_assets", "COPY deploy ./deploy" in docker_text, "deploy assets"),
        ("dockerfile_omits_deployment_review", "COPY deployment_review" not in docker_text, "deployment review artifacts excluded"),
        ("dockerignore_exists", dockerignore.exists(), ".dockerignore"),
        ("dockerignore_excludes_local_data", ".local_data" in ignore_text, ".local_data"),
        ("dockerignore_excludes_env", ".env" in ignore_text and ".env.*" in ignore_text, ".env patterns"),
        ("dockerignore_excludes_key_files", "*.key" in ignore_text and "*.pem" in ignore_text, "key patterns"),
        ("dockerignore_excludes_large_artifacts", "*.safetensors" in ignore_text and "*.onnx" in ignore_text and "*.arrow" in ignore_text, "large data/model patterns"),
        ("compose_public_mini_exists", (root / "docker/compose.public-mini.yml").exists(), "docker/compose.public-mini.yml"),
        ("compose_network_disabled", 'network_mode: "none"' in compose_text, "network_mode none"),
        ("compose_read_only_rootfs", "read_only: true" in compose_text, "read_only"),
        ("compose_no_new_privileges", "no-new-privileges:true" in compose_text, "no-new-privileges"),
        ("compose_cap_drop_all", "cap_drop:" in compose_text and "ALL" in compose_text, "cap_drop ALL"),
        ("compose_has_resource_limits", "pids_limit:" in compose_text and "mem_limit:" in compose_text and "cpus:" in compose_text, "resource limits"),
        ("docker_helper_scripts_exist", all((root / path).exists() for path in ["docker/run_public_mini.sh", "docker/run_governance_job.sh", "docker/healthcheck.sh"]), "helper scripts"),
        ("makefile_docker_targets", all(target in make_text for target in ["docker-build", "docker-validate", "docker-run-public-mini", "docker-compose-public-mini"]), "Makefile targets"),
        ("public_mini_job_config", (root / "configs/jobs/public_mini_governance_job.yaml").exists(), "job config"),
        ("promotion_decision_schema", (root / "schemas/promotion_decision.schema.json").exists(), "promotion schema"),
    ]
    rows = [{"check": name, "status": "PASS" if passed else "FAIL", "detail": detail} for name, passed, detail in checks]
    failures = [row for row in rows if row["status"] == "FAIL"]
    result_class = "DOCKER_STATIC_VALIDATION_PASSED" if not failures else "DOCKER_STATIC_VALIDATION_FAILED"
    payload = {
        "schema_version": "1.0",
        "result_class": result_class,
        "checks_passed": len(rows) - len(failures),
        "checks_total": len(rows),
        "failures": failures,
        "raw_data_committed": False,
        "secrets_committed": False,
        "private_paths_committed": False,
        "live_cloud_validation_claimed": False,
        "production_readiness_claimed": False,
    }
    write_json(output_root / "docker_static_validation.json", payload)
    _write_csv(output_root / "docker_static_validation.csv", rows)
    write_md(output_root / "docker_static_validation_report.md", f"# Docker Static Validation\n\nResult class: `{result_class}`.\n\nChecks passed: {payload['checks_passed']} / {payload['checks_total']}.")
    return payload
