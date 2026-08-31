#!/usr/bin/env python3
"""Validate and exclusively materialize one failed FULL-run closure."""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MAX_RUN_ID = 9_223_372_036_854_775_807
RUN_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,18}$", re.ASCII)
EXECUTION_WORKFLOW_PATH = ".github/workflows/research-full-execute.yml"
EXECUTION_WORKFLOW_NAME = "Research FULL future-beacon execution"
EXECUTION_EVENT = "workflow_dispatch"
CLOSURE_ELIGIBLE_CONCLUSIONS = frozenset({"cancelled"})
CLOSURE_PROTOCOL_VERSION = "full_execution_closure.v2"


class ClosureValidationError(ValueError):
    pass


def canonical_run_id(raw: object) -> str:
    if not isinstance(raw, str) or RUN_ID_PATTERN.fullmatch(raw) is None:
        raise ClosureValidationError("run ID must be canonical positive ASCII decimal")
    value = int(raw)
    if not 1 <= value <= MAX_RUN_ID or str(value) != raw:
        raise ClosureValidationError("run ID is outside the supported range")
    return raw


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ClosureValidationError(f"{label} must be an integer")
    if positive and value < 1:
        raise ClosureValidationError(f"{label} must be positive")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ClosureValidationError(f"{label} must be nonempty text")
    return value


def validate_server_run(
    raw_run_id: object,
    run: Mapping[str, Any],
    workflow: Mapping[str, Any],
    *,
    repository: str,
    subject_commit: str,
    seal_run_id: str,
    seal_commit_sha: str,
    verified_at_utc: str | None = None,
) -> dict[str, Any]:
    run_id = canonical_run_id(raw_run_id)
    expected_id = int(run_id)
    workflow_id = _integer(workflow.get("id"), "workflow.id", positive=True)
    if _text(workflow.get("path"), "workflow.path") != EXECUTION_WORKFLOW_PATH:
        raise ClosureValidationError("server workflow path mismatch")
    if _integer(run.get("id"), "run.id", positive=True) != expected_id:
        raise ClosureValidationError("server run ID mismatch")
    if _text(run.get("repository", {}).get("full_name"), "run.repository") != repository:
        raise ClosureValidationError("server repository mismatch")
    head_repository = run.get("head_repository")
    if head_repository is not None and (
        not isinstance(head_repository, Mapping)
        or head_repository.get("full_name") != repository
    ):
        raise ClosureValidationError("server head repository mismatch")
    if _integer(run.get("workflow_id"), "run.workflow_id", positive=True) != workflow_id:
        raise ClosureValidationError("server workflow ID mismatch")
    run_path = _text(run.get("path"), "run.path").split("@", 1)[0]
    if run_path != EXECUTION_WORKFLOW_PATH:
        raise ClosureValidationError("server run workflow path mismatch")
    if run.get("event") != EXECUTION_EVENT:
        raise ClosureValidationError("server run event mismatch")
    if run.get("head_sha") != subject_commit:
        raise ClosureValidationError("server run head SHA mismatch")
    if run.get("status") != "completed":
        raise ClosureValidationError("server run is not completed")
    conclusion = run.get("conclusion")
    if conclusion not in CLOSURE_ELIGIBLE_CONCLUSIONS:
        raise ClosureValidationError("server run conclusion is not closure eligible")
    run_attempt = _integer(run.get("run_attempt"), "run.run_attempt", positive=True)
    expected_title = f"FULL execute {subject_commit} sealrun-{seal_run_id}"
    display_title = _text(run.get("display_title"), "run.display_title")
    if display_title != expected_title:
        raise ClosureValidationError("server run display title mismatch")
    timestamp = verified_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "2.0",
        "closure_protocol_version": CLOSURE_PROTOCOL_VERSION,
        "closure_status": "ABORTED_OR_INCOMPLETE",
        "canonical_run_id": run_id,
        "repository": repository,
        "workflow_id": workflow_id,
        "workflow_name": EXECUTION_WORKFLOW_NAME,
        "workflow_path": run_path,
        "event": EXECUTION_EVENT,
        "head_sha": subject_commit,
        "head_branch": run.get("head_branch") if isinstance(run.get("head_branch"), str) else None,
        "run_attempt": run_attempt,
        "status": "completed",
        "conclusion": conclusion,
        "display_title": display_title,
        "html_url": run.get("html_url") if isinstance(run.get("html_url"), str) else None,
        "api_url": run.get("url") if isinstance(run.get("url"), str) else None,
        "verified_at_utc": timestamp,
        "frozen_execution_identity": {
            "subject_commit": subject_commit,
            "seal_workflow_run_id": seal_run_id,
            "seal_commit_sha": seal_commit_sha,
        },
        "validation_status": "SERVER_RUN_VERIFIED",
        "server_side_run_verified": True,
        "destination_containment_verified": False,
        "caller_metadata_authoritative": False,
        "same_seal_required_for_resume": True,
        "fallback_round_permitted": False,
        "publication_independent_of_scientific_direction": True,
        "execution_manifest_present": False,
        "output_hashes_verified": False,
    }


def _link_or_reparse(path: Path) -> bool:
    info = path.lstat()
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse)


def write_closure_exclusive(
    results_tree_value: str,
    run_id_value: str,
    record: Mapping[str, Any],
) -> Path:
    run_id = canonical_run_id(run_id_value)
    root_input = Path(results_tree_value)
    if not root_input.is_absolute() or not root_input.exists() or _link_or_reparse(root_input):
        raise ClosureValidationError("results repository root is invalid")
    root = root_input.resolve(strict=True)
    if os.path.normcase(str(root)) != os.path.normcase(os.path.abspath(root_input)):
        raise ClosureValidationError("results repository root alias is forbidden")
    git_root = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if os.path.normcase(str(root)) != os.path.normcase(str(Path(git_root).resolve(strict=True))):
        raise ClosureValidationError("results root is not the canonical Git root")
    if record.get("canonical_run_id") != run_id or record.get("server_side_run_verified") is not True:
        raise ClosureValidationError("closure record is not bound to the verified run")
    executions = root / "executions"
    if executions.exists() or executions.is_symlink():
        if _link_or_reparse(executions) or not executions.is_dir():
            raise ClosureValidationError("executions root is not a regular directory")
    destination = executions / run_id
    if destination.parent != executions or destination.exists() or destination.is_symlink():
        raise ClosureValidationError("closure destination already exists or escaped containment")
    if not executions.exists():
        os.mkdir(executions)
    if _link_or_reparse(executions):
        raise ClosureValidationError("executions root changed during validation")
    os.mkdir(destination)
    output = destination / "execution-closure.json"
    final_record = dict(record)
    final_record["destination_containment_verified"] = True
    payload = json.dumps(final_record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return output


def _json_env(name: str) -> Mapping[str, Any]:
    value = json.loads(os.environ[name], parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, Mapping):
        raise ClosureValidationError(f"{name} must contain a JSON object")
    return value


def main() -> int:
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "canonicalize":
        print(canonical_run_id(os.environ.get("ABORTED_EXECUTION_RUN_ID")))
        return 0
    if command == "validate":
        record = validate_server_run(
            os.environ.get("ABORTED_EXECUTION_RUN_ID"),
            _json_env("RUN_JSON"),
            _json_env("WORKFLOW_JSON"),
            repository=os.environ["GITHUB_REPOSITORY"],
            subject_commit=os.environ["SUBJECT_COMMIT"],
            seal_run_id=os.environ["SEAL_RUN_ID"],
            seal_commit_sha=os.environ["SEAL_COMMIT_SHA"],
        )
        print(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    if command == "write":
        record = json.loads(base64.b64decode(os.environ["CLOSURE_RECORD_B64"]).decode("utf-8"))
        print(write_closure_exclusive(os.environ["RESULTS_TREE"], os.environ["CANONICAL_RUN_ID"], record))
        return 0
    raise ClosureValidationError("expected canonicalize, validate, or write command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ClosureValidationError, KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"closure validation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
