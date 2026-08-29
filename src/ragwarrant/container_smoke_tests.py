from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any

from ragwarrant.container_runtime import load_runtime_diagnostics
from ragwarrant.generative_validation_common import write_json, write_md


SMOKE_RESULT_CLASSES = {
    "DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
    "PODMAN_RUNTIME_VALIDATED_PUBLIC_MINI",
    "COLIMA_DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
    "CONTAINER_RUNTIME_STATIC_VALIDATION_ONLY",
    "CONTAINER_RUNTIME_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE",
    "CONTAINER_RUNTIME_VALIDATION_SKIPPED_ENGINE_UNAVAILABLE",
    "CONTAINER_RUNTIME_VALIDATION_FAILED",
    "CONTAINER_RUNTIME_VALIDATION_FAILED_PUBLICATION_HYGIENE",
}

DOCKER_HARDENED_RUN_FLAGS = [
    "--network",
    "none",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,size=64m",
    "--security-opt",
    "no-new-privileges",
    "--cap-drop",
    "ALL",
    "--pids-limit",
    "256",
    "--memory",
    "1g",
    "--cpus",
    "2",
]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["step", "status", "detail"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _run(command: list[str], root: Path, timeout: int = 300) -> tuple[bool, str]:
    proc = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=timeout, check=False)
    text = (proc.stderr or proc.stdout or "").strip()
    return proc.returncode == 0, text.splitlines()[-1][:160] if text else ""


def run_container_smoke_tests(root: Path, *, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    diagnostics = load_runtime_diagnostics(output_root / "container_runtime_diagnostics.json")
    docker_cli = bool(diagnostics.get("docker_cli_present"))
    docker_daemon = bool(diagnostics.get("docker_daemon_available"))
    podman_ready = bool(diagnostics.get("podman_ready"))
    colima_ready = bool(diagnostics.get("colima_ready"))
    steps: list[dict[str, Any]] = []
    if docker_daemon:
        engine = "docker"
        result_class = "CONTAINER_RUNTIME_VALIDATION_FAILED"
        build_ok, build_detail = _run(["docker", "build", "-t", "ragwarrant:local", "."], root)
        steps.append({"step": "docker_build", "status": "PASS" if build_ok else "FAIL", "detail": build_detail})
        help_ok = validate_ok = mini_ok = compose_ok = False
        if build_ok:
            help_ok, help_detail = _run(["docker", "run", "--rm", *DOCKER_HARDENED_RUN_FLAGS, "ragwarrant:local", "--help"], root)
            steps.append({"step": "container_help", "status": "PASS" if help_ok else "FAIL", "detail": help_detail})
            validate_ok, validate_detail = _run(["docker", "run", "--rm", *DOCKER_HARDENED_RUN_FLAGS, "ragwarrant:local", "validate-bundle"], root)
            steps.append({"step": "container_validate_bundle", "status": "PASS" if validate_ok else "FAIL", "detail": validate_detail})
            (root / "docker_outputs").mkdir(exist_ok=True)
            mini_ok, mini_detail = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    *DOCKER_HARDENED_RUN_FLAGS,
                    "-v",
                    f"{root / 'docker_outputs'}:/outputs",
                    "ragwarrant:local",
                    "run-governance-job",
                    "--config",
                    "configs/jobs/public_mini_governance_job.yaml",
                    "--output-root",
                    "/outputs",
                    "--decision-out",
                    "/outputs/promotion_decision.json",
                ],
                root,
            )
            steps.append({"step": "container_public_mini", "status": "PASS" if mini_ok else "FAIL", "detail": mini_detail})
            compose_ok, compose_detail = _run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "docker/compose.public-mini.yml",
                    "up",
                    "--build",
                    "--abort-on-container-exit",
                    "--exit-code-from",
                    "ragwarrant-public-mini",
                ],
                root,
            )
            steps.append({"step": "docker_compose_public_mini", "status": "PASS" if compose_ok else "FAIL", "detail": compose_detail})
        if build_ok and help_ok and validate_ok and mini_ok and compose_ok:
            result_class = "DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI"
    elif docker_cli or podman_ready or colima_ready:
        engine = "docker" if docker_cli else "podman" if podman_ready else "colima"
        result_class = "CONTAINER_RUNTIME_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE"
        steps.append({"step": "runtime", "status": "SKIP", "detail": "container CLI present but usable daemon/machine unavailable"})
    else:
        engine = "none"
        result_class = "CONTAINER_RUNTIME_VALIDATION_SKIPPED_ENGINE_UNAVAILABLE"
        steps.append({"step": "runtime", "status": "SKIP", "detail": "no supported container engine available"})
    promotion_copy = output_root / "promotion_decision_container.json"
    docker_output_decision = root / "docker_outputs/promotion_decision.json"
    if docker_output_decision.exists() and "VALIDATED" in result_class:
        promotion_copy.write_text(docker_output_decision.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        write_json(
            promotion_copy,
            {
                "schema_version": "1.0",
                "decision": "INCONCLUSIVE",
                "result_class": result_class,
                "decision_reason": "container runtime validation did not produce a runtime promotion decision",
            },
        )
    inventory_rows = []
    if (root / "docker_outputs").exists():
        for path in sorted((root / "docker_outputs").rglob("*")):
            if path.is_file():
                inventory_rows.append({"path": path.relative_to(root / "docker_outputs").as_posix(), "bytes": path.stat().st_size})
    if not inventory_rows:
        inventory_rows = [{"path": "<no-runtime-output-files>", "bytes": 0}]
    manifest = {
        "schema_version": "1.0",
        "result_class": result_class,
        "engine_selected": engine,
        "docker_build_result": next((row["status"] for row in steps if row["step"] == "docker_build"), "not_run"),
        "docker_validate_result": next((row["status"] for row in steps if row["step"] == "container_validate_bundle"), "not_run"),
        "docker_public_mini_result": next((row["status"] for row in steps if row["step"] == "container_public_mini"), "not_run"),
        "docker_compose_public_mini_result": next((row["status"] for row in steps if row["step"] == "docker_compose_public_mini"), "not_run"),
        "skip_reason": "" if "VALIDATED" in result_class else steps[-1]["detail"],
        "static_validation_required": True,
        "raw_data_committed": False,
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "secrets_committed": False,
        "private_paths_committed": False,
        "live_cloud_validation_claimed": False,
        "production_readiness_claimed": False,
        "official_platform_benchmarking_claimed": False,
        "hardened_runtime_flags": {
            "network_none": True,
            "read_only_root_filesystem": True,
            "tmpfs_tmp": True,
            "no_new_privileges": True,
            "cap_drop_all": True,
            "pids_limit": 256,
            "memory_limit": "1g",
            "cpus": "2",
        },
    }
    write_json(output_root / "container_smoke_test_manifest.json", manifest)
    _write_csv(output_root / "container_smoke_test_results.csv", steps)
    _write_csv(output_root / "container_output_file_inventory.csv", inventory_rows)
    write_md(
        output_root / "container_smoke_test_report.md",
        f"""
# Container Smoke Test

Result class: `{result_class}`

Engine selected: `{engine}`

Skip reason: `{manifest['skip_reason']}`

This is local container validation only. It does not claim live cloud validation, official platform benchmarking, or production operation.
""",
    )
    results_root = root / "results/docker_hardening"
    write_json(results_root / "claim_update.json", manifest)
    write_md(results_root / "executive_summary.md", f"Docker/container smoke-test result: `{result_class}`.")
    return manifest
