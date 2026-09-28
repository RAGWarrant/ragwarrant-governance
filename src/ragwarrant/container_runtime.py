# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import write_json, write_md


CONTAINER_RUNTIME_RESULT_CLASSES = {
    "CONTAINER_RUNTIME_DOCKER_READY",
    "CONTAINER_RUNTIME_PODMAN_READY",
    "CONTAINER_RUNTIME_COLIMA_READY",
    "CONTAINER_RUNTIME_CLI_PRESENT_DAEMON_UNAVAILABLE",
    "CONTAINER_RUNTIME_UNAVAILABLE",
    "CONTAINER_RUNTIME_DIAGNOSTIC_FAILED",
}


def _run(command: list[str], timeout: int = 10) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return False, type(exc).__name__
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip().splitlines()[0][:160] if (proc.stderr or proc.stdout) else ""


def diagnose_container_runtime(root: Path, *, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    docker_cli = shutil.which("docker") is not None
    docker_daemon = False
    docker_compose = False
    buildx = False
    if docker_cli:
        docker_daemon, _ = _run(["docker", "info"])
        docker_compose, _ = _run(["docker", "compose", "version"])
        buildx, _ = _run(["docker", "buildx", "version"])
    legacy_compose = shutil.which("docker-compose") is not None
    podman_cli = shutil.which("podman") is not None
    podman_ready = False
    if podman_cli:
        podman_ready, _ = _run(["podman", "info"])
    colima_cli = shutil.which("colima") is not None
    colima_ready = False
    if colima_cli:
        colima_ready, _ = _run(["colima", "status"])
    nerdctl_cli = shutil.which("nerdctl") is not None
    if docker_cli and docker_daemon:
        result_class = "CONTAINER_RUNTIME_DOCKER_READY"
    elif podman_cli and podman_ready:
        result_class = "CONTAINER_RUNTIME_PODMAN_READY"
    elif colima_cli and colima_ready:
        result_class = "CONTAINER_RUNTIME_COLIMA_READY"
    elif docker_cli or podman_cli or colima_cli or nerdctl_cli:
        result_class = "CONTAINER_RUNTIME_CLI_PRESENT_DAEMON_UNAVAILABLE"
    else:
        result_class = "CONTAINER_RUNTIME_UNAVAILABLE"
    payload = {
        "schema_version": "1.0",
        "result_class": result_class,
        "docker_cli_present": docker_cli,
        "docker_daemon_available": docker_daemon,
        "docker_compose_plugin_available": docker_compose,
        "docker_compose_legacy_available": legacy_compose,
        "podman_cli_present": podman_cli,
        "podman_ready": podman_ready,
        "colima_cli_present": colima_cli,
        "colima_ready": colima_ready,
        "nerdctl_cli_present": nerdctl_cli,
        "buildx_available": buildx,
        "docker_socket_user_access": docker_daemon,
        "private_paths_exported": False,
        "secrets_exported": False,
        "hostnames_exported": False,
        "ip_addresses_exported": False,
    }
    write_json(output_root / "container_runtime_diagnostics.json", payload)
    write_md(
        output_root / "container_runtime_diagnostics.md",
        f"""
# Container Runtime Diagnostics

Result class: `{result_class}`

- Docker CLI present: `{docker_cli}`
- Docker daemon available: `{docker_daemon}`
- Docker Compose plugin available: `{docker_compose}`
- Podman ready: `{podman_ready}`
- Colima ready: `{colima_ready}`

No secrets, hostnames, private paths, IP addresses, MAC addresses, or environment dumps are exported.
""",
    )
    return payload


def load_runtime_diagnostics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
