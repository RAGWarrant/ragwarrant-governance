from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import validate_full_closure as closure_validation


SUBJECT_COMMIT = "ab" * 20
REPOSITORY = "RAGWarrant/ragwarrant-governance"


def _workflow() -> dict[str, object]:
    return {"id": 77, "path": closure_validation.EXECUTION_WORKFLOW_PATH}


def _run(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 123,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
        "workflow_id": 77,
        "path": f"{closure_validation.EXECUTION_WORKFLOW_PATH}@refs/heads/frozen",
        "event": "workflow_dispatch",
        "head_sha": SUBJECT_COMMIT,
        "head_branch": f"ragwarrant-full-subject-{SUBJECT_COMMIT}",
        "status": "completed",
        "conclusion": "cancelled",
        "run_attempt": 1,
        "display_title": f"FULL execute {SUBJECT_COMMIT} sealrun-456",
        "html_url": "https://github.example/actions/runs/123",
        "url": "https://api.github.example/actions/runs/123",
    }
    value.update(updates)
    return value


def _record(
    run: dict[str, object] | None = None,
    workflow: dict[str, object] | None = None,
) -> dict[str, object]:
    return closure_validation.validate_server_run(
        "123",
        run or _run(),
        workflow or _workflow(),
        repository=REPOSITORY,
        subject_commit=SUBJECT_COMMIT,
        seal_run_id="456",
        seal_commit_sha="ef" * 20,
        verified_at_utc="2026-08-31T00:00:00Z",
    )


def test_run_id_accepts_canonical_signed_64_bit_maximum() -> None:
    assert closure_validation.canonical_run_id("9223372036854775807") == (
        "9223372036854775807"
    )


@pytest.mark.parametrize(
    "value",
    [
        "", "0", "-1", "+1", "01", "1.0", "1e3", "../1",
        "1/../../x", "1;echo", " 1", "1\t", "1\n", "１２３",
        "9223372036854775808",
    ],
)
def test_run_id_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(closure_validation.ClosureValidationError):
        closure_validation.canonical_run_id(value)


@pytest.mark.parametrize(
    ("run_update", "workflow_update"),
    [
        ({"id": 124}, {}),
        ({"repository": {"full_name": "other/repo"}}, {}),
        ({"head_repository": {"full_name": "other/repo"}}, {}),
        ({"workflow_id": 78}, {}),
        ({"path": ".github/workflows/other.yml"}, {}),
        ({}, {"path": ".github/workflows/other.yml"}),
        ({"event": "push"}, {}),
        ({"head_sha": "00" * 20}, {}),
        ({"status": "in_progress", "conclusion": None}, {}),
        ({"conclusion": "success"}, {}),
        ({"conclusion": "failure"}, {}),
        ({"conclusion": "neutral"}, {}),
        ({"run_attempt": 0}, {}),
        ({"display_title": "caller-selected"}, {}),
    ],
)
def test_server_identity_rejection_precedes_generation(
    run_update: dict[str, object],
    workflow_update: dict[str, object],
    tmp_path: Path,
) -> None:
    generator_called = False
    with pytest.raises(closure_validation.ClosureValidationError):
        _record(_run(**run_update), {**_workflow(), **workflow_update})
        generator_called = True
    assert generator_called is False
    assert not list(tmp_path.iterdir())


def test_latest_successful_attempt_cannot_be_closed_as_old_failure() -> None:
    with pytest.raises(closure_validation.ClosureValidationError):
        _record(_run(run_attempt=2, conclusion="success"))


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)


def test_validated_record_uses_exact_contained_path_and_server_fields(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _git_init(results)
    record_input = _record(_run(caller_path="../../escape"))
    assert "caller_path" not in record_input
    output = closure_validation.write_closure_exclusive(
        str(results.resolve()), "123", record_input
    )
    assert output == results.resolve() / "executions/123/execution-closure.json"
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["canonical_run_id"] == "123"
    assert record["workflow_id"] == 77
    assert record["conclusion"] == "cancelled"
    assert record["server_side_run_verified"] is True
    assert record["destination_containment_verified"] is True
    assert record["caller_metadata_authoritative"] is False


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    results = tmp_path / "results"
    destination = results / "executions/123"
    destination.mkdir(parents=True)
    _git_init(results)
    marker = destination / "execution-closure.json"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(closure_validation.ClosureValidationError):
        closure_validation.write_closure_exclusive(
            str(results.resolve()), "123", _record()
        )
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_destination_cannot_be_selected_with_path_input(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _git_init(results)
    with pytest.raises(closure_validation.ClosureValidationError):
        closure_validation.write_closure_exclusive(
            str(results.resolve()), "../123", _record()
        )
    assert not (results / "executions").exists()


@pytest.mark.parametrize("link_target", ["executions", "executions/123"])
def test_symlinked_destination_components_fail(
    tmp_path: Path,
    link_target: str,
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _git_init(results)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = results / link_target
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(closure_validation.ClosureValidationError):
        closure_validation.write_closure_exclusive(
            str(results.resolve()), "123", _record()
        )
    assert not list(outside.iterdir())


def test_invalid_input_performs_zero_api_or_repository_writes(tmp_path: Path) -> None:
    api_called = False
    repository_write_called = False
    with pytest.raises(closure_validation.ClosureValidationError):
        closure_validation.canonical_run_id("../123")
        api_called = True
        repository_write_called = True
    assert api_called is repository_write_called is False
    assert not list(tmp_path.iterdir())


def test_workflow_validates_before_artifact_or_repository_write() -> None:
    workflow = Path(".github/workflows/research-full-closure.yml").read_text(
        encoding="utf-8"
    )
    validation = workflow.index("Validate the server-side execution identity before writes")
    artifact = workflow.index("actions/download-artifact")
    repository_write = workflow.index("Append the cancellation record")
    assert validation < artifact < repository_write
    prewrite = workflow[validation:artifact]
    assert "mkdir" not in prewrite and "git clone" not in prewrite
    assert "ABORTED_EXECUTION_RUN_ID: ${{ inputs.aborted_execution_run_id }}" in workflow
    assert "actions/runs/${canonical_run_id}" in workflow
    assert "actions/workflows/research-full-execute.yml" in workflow
    assert "actions: write" not in workflow
