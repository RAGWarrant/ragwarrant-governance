# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import write_json, write_md


SECURITY_SCAN_RESULT_CLASSES = {
    "CONTAINER_SECURITY_SCANS_COMPLETED",
    "CONTAINER_SECURITY_SCANS_PARTIAL",
    "CONTAINER_SECURITY_SCANS_SKIPPED_TOOLS_UNAVAILABLE",
    "CONTAINER_SECURITY_SCANS_SKIPPED_IMAGE_UNAVAILABLE",
    "CONTAINER_SECURITY_SCANS_FAILED_CRITICAL_FINDINGS",
}


def run_optional_container_security_scans(root: Path, *, output_root: Path) -> dict[str, Any]:
    tools = ["hadolint", "trivy", "grype", "syft", "docker_scout"]
    rows: list[dict[str, Any]] = []
    available = 0
    for tool in tools:
        if tool == "docker_scout":
            present = (
                shutil.which("docker") is not None
                and subprocess.run(["docker", "scout", "version"], cwd=root, capture_output=True, text=True, check=False).returncode == 0
            )
        else:
            present = shutil.which(tool) is not None
        available += 1 if present else 0
        rows.append({"tool": tool, "status": "AVAILABLE_NOT_RUN" if present else "SKIPPED_TOOL_UNAVAILABLE", "detail": "optional scanner"})
    result_class = "CONTAINER_SECURITY_SCANS_SKIPPED_TOOLS_UNAVAILABLE" if available == 0 else "CONTAINER_SECURITY_SCANS_PARTIAL"
    payload = {
        "schema_version": "1.0",
        "result_class": result_class,
        "tools_checked": tools,
        "tools_available": available,
        "image_scan_completed": False,
        "critical_findings": 0,
        "private_paths_exported": False,
        "secrets_exported": False,
        "large_scan_outputs_committed": False,
    }
    write_json(output_root / "container_security_scan_manifest.json", payload)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "container_security_scan_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["tool", "status", "detail"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write_md(output_root / "container_security_scan_report.md", f"# Optional Container Security Scans\n\nResult class: `{result_class}`.\n\nOptional scanners are not required for publication validation.")
    return payload
