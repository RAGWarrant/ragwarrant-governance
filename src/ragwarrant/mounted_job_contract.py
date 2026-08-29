from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import write_json
from ragwarrant.storage import build_storage_sink
from ragwarrant.storage.base import StorageUnavailable


EXIT_OK = 0
EXIT_CONFIG_OR_INPUT_ERROR = 2
EXIT_RUNTIME_FAILURE = 4


def mounted_contract_paths() -> dict[str, Path]:
    return {
        "input_dir": Path(os.environ.get("RAGWARRANT_INPUT_DIR", "/inputs")),
        "output_dir": Path(os.environ.get("RAGWARRANT_OUTPUT_DIR") or os.environ.get("RAGWARRANT_OUTPUT_ROOT", "/outputs")),
    }


def _safe_path_label(path: Path) -> str:
    if path.as_posix() in {"/inputs", "/outputs"}:
        return path.as_posix()
    return "<configured-mounted-path>"


def check_mounted_job_contract(*, write_probe: bool = False, output_root: Path | None = None) -> tuple[int, dict[str, Any]]:
    paths = mounted_contract_paths()
    input_dir = paths["input_dir"]
    output_dir = paths["output_dir"]
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "contract": "ragwarrant_mounted_governance_job_io_v1",
        "input_mount": _safe_path_label(input_dir),
        "output_mount": _safe_path_label(output_dir),
        "input_dir_exists": input_dir.exists(),
        "output_dir_exists": output_dir.exists(),
        "output_dir_writable": False,
        "raw_text_exported": False,
        "private_paths_exported": False,
        "secrets_exported": False,
        "fallbacks": [],
    }
    if not input_dir.exists():
        report["fallbacks"].append("FALLBACK_INPUT_DIR_NOT_PRESENT")
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            report["fallbacks"].append("FALLBACK_OUTPUT_DIR_NOT_CREATABLE")
    if output_dir.exists():
        try:
            probe = output_dir / ".ragwarrant_write_probe"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink(missing_ok=True)
            report["output_dir_writable"] = True
        except OSError:
            report["fallbacks"].append("FALLBACK_OUTPUT_DIR_NOT_WRITABLE")
    if write_probe and report["output_dir_writable"]:
        write_json(output_dir / "mounted_contract_probe.json", report)
    destination = output_root or output_dir
    if report["output_dir_writable"] and destination:
        write_json(destination / "mounted_job_contract_report.json", report)
    status = EXIT_OK if report["input_dir_exists"] and report["output_dir_writable"] else EXIT_CONFIG_OR_INPUT_ERROR
    return status, report


def exercise_storage_mode(mode: str, *, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    sample = output_root / "sample_artifact.json"
    sample.write_text(json.dumps({"raw_text_exported": False}, sort_keys=True) + "\n", encoding="utf-8")
    result: dict[str, Any] = {
        "mode": mode,
        "available": False,
        "fallback": "",
        "uri": "",
        "secrets_logged": False,
        "raw_text_exported": False,
    }
    try:
        sink = build_storage_sink(mode=mode, output_root=output_root)
        stored = sink.put_file(sample, f"{mode}/sample_artifact.json")
        result.update({"available": True, "uri": stored.uri})
    except StorageUnavailable as exc:
        result["fallback"] = f"FALLBACK_{mode.upper()}_UNAVAILABLE"
        result["reason"] = str(exc)
    return result

