from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path

from ragwarrant.generative_validation_common import write_csv, write_json, write_md


def _safe_cpu_label() -> str:
    try:
        label = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=2).strip()
    except Exception:
        label = platform.machine()
    return label.replace(os.environ.get("USER", ""), "<user>")


def _memory_gb() -> float:
    try:
        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=2).strip()
        return round(int(raw) / (1024**3), 2)
    except Exception:
        return 0.0


def run_aim_hardware_characterization(root: Path, *, output_root: Path) -> dict[str, object]:
    start = time.perf_counter()
    mini_manifest = root / "artifacts/public_mini_reproduction/mini_reproduction_manifest.json"
    selector_manifest = root / "artifacts/selector_ablation_matrix/selector_ablation_manifest.json"
    runtime_rows = []
    for label, path in [("public_mini_reproduction_artifact_check", mini_manifest), ("selector_ablation_artifact_check", selector_manifest)]:
        t0 = time.perf_counter()
        exists = path.exists()
        runtime_rows.append({"benchmark": label, "runtime_ms": round((time.perf_counter() - t0) * 1000, 3), "status": "available" if exists else "missing"})
    artifact_rows = []
    for rel in ["artifacts/public_mini_reproduction", "artifacts/selector_ablation_matrix", "artifacts/generative_llm_validation/crag_quality_risk_guardrail_v2"]:
        total = sum(path.stat().st_size for path in (root / rel).rglob("*") if path.is_file()) if (root / rel).exists() else 0
        artifact_rows.append({"artifact_group": rel.replace("/", "::"), "size_bytes": total})
    generator_provider = os.environ.get("RAGWARRANT_GENERATOR_PROVIDER", "not_configured")
    result = {
        "suite": "ragwarrant_aim_hardware_characterization_v1",
        "result_class": "AIM_HARDWARE_CHARACTERIZATION_COMPLETED",
        "machine_role": os.environ.get("RAGWARRANT_AIM_HARDWARE_ROLE", "local_validation_node"),
        "public_label": os.environ.get("RAGWARRANT_AIM_HARDWARE_PUBLIC_LABEL", "AIM local validation node"),
        "cpu_model_sanitized": _safe_cpu_label(),
        "ram_gb": _memory_gb(),
        "gpu_count": "",
        "gpu_names_sanitized": [],
        "python_version": platform.python_version(),
        "os_family": platform.system(),
        "generator_provider": generator_provider,
        "generator_model_id": os.environ.get("RAGWARRANT_GENERATOR_MODEL", "not_configured"),
        "official_platform_benchmark": False,
        "hostnames_exported": False,
        "private_paths_exported": False,
        "ip_addresses_exported": False,
        "mac_addresses_exported": False,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
    }
    write_json(output_root / "hardware_manifest.json", result)
    write_csv(output_root / "runtime_benchmark_results.csv", ["benchmark", "runtime_ms", "status"], runtime_rows)
    write_csv(output_root / "generator_throughput_results.csv", ["metric", "value"], [{"metric": "generator_throughput_status", "value": "not_measured_without_explicit_runtime"}])
    write_csv(output_root / "artifact_size_summary.csv", ["artifact_group", "size_bytes"], artifact_rows)
    write_md(
        output_root / "hardware_characterization_report.md",
        """
# AIM Hardware Characterization

This is local AIM hardware performance characterization, not official platform benchmarking.

The report stores a sanitized CPU label, coarse memory value, Python/OS family, artifact sizes, and lightweight runtime checks. It does not store hostnames, usernames, IP addresses, MAC addresses, private paths, or secrets.
""",
    )
    return result
