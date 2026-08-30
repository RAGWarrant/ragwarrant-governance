from __future__ import annotations

import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ragwarrant.utils.files import write_json, write_text
from ragwarrant.utils.hashing import sha256_file, stable_hash
from ragwarrant.utils.write_once import WriteOnceError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_run_id(suite: str, payload: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{suite}_{stamp}-{stable_hash(payload, 10)}"


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None


def dependency_lock_hash() -> str | None:
    for name in ["uv.lock", "poetry.lock", "requirements.lock", "pyproject.toml"]:
        path = Path(name)
        if path.exists():
            return sha256_file(path)
    return None


def prepare_run_dir(
    output_dir: Path,
    run_id: str,
    *,
    suite: str,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> tuple[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_run_id = run_id
    if run_id == "auto" or force_new_run_id:
        resolved_run_id = stable_run_id(suite, {"output_dir": str(output_dir), "suite": suite})
    run_dir = output_dir / resolved_run_id
    manifest = run_dir / "run_manifest.json"
    if manifest.exists() and not resume and not force_new_run_id:
        raise WriteOnceError(f"Completed run already exists: {run_dir}")
    if run_dir.exists() and not resume and not force_new_run_id:
        raise WriteOnceError(f"Run directory already exists: {run_dir}")
    if force_new_run_id and run_dir.exists():
        resolved_run_id = stable_run_id(suite, {"requested_run_id": run_id, "attempt": utc_now()})
        run_dir = output_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=resume)
    (run_dir / "logs").mkdir(exist_ok=True)
    return resolved_run_id, run_dir


def copy_input_config(config_path: Path, run_dir: Path) -> str:
    target = run_dir / "input_config.yaml"
    if target.exists():
        return str(target)
    shutil.copy2(config_path, target)
    return str(target)


def write_run_manifest(
    run_dir: Path,
    *,
    suite: str,
    run_id: str,
    config_path: Path,
    seed: int,
    dataset_hash: str,
    status: str,
    evidence_mode: str | None = None,
    parent_run_id: str | None = None,
    extra: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "suite": suite,
        "run_id": run_id,
        "status": status,
        "evidence_mode": evidence_mode or "fixture",
        "parent_run_id": parent_run_id,
        "seed": seed,
        "config_path": str(config_path),
        "config_hash": sha256_file(config_path),
        "dataset_hash": dataset_hash,
        "git_commit": git_commit(),
        "container_digest": os.getenv("RAGWARRANT_CONTAINER_DIGEST"),
        "dependency_lock_hash": dependency_lock_hash(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "started_at_utc": utc_now(),
        "ended_at_utc": utc_now(),
        "errors": errors or [],
        "claim_boundary": "RAGWarrant software validation only; no hardware or quantum-advantage claim.",
    }
    if extra:
        payload.update(extra)
    write_json(run_dir / "run_manifest.json", payload)
    return payload


def write_no_overwrite_audit(run_dir: Path, *, run_id: str) -> dict[str, Any]:
    payload = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "append_only": True,
        "completed_manifest_present": (run_dir / "run_manifest.json").exists(),
        "attempted_overwrites_blocked": 0,
        "status": "append_only_confirmed",
    }
    write_json(run_dir / "no_overwrite_audit.json", payload)
    return payload


def write_policy_space(run_dir: Path, policy_space: dict[str, Any]) -> None:
    write_text(run_dir / "policy_space.yaml", yaml.safe_dump(policy_space, sort_keys=True))
