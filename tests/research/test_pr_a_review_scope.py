from __future__ import annotations

import hashlib
import json
import subprocess
from subprocess import CompletedProcess
from pathlib import Path

import pytest

from ragwarrant.research import review_scope_authority as scope


ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def synthetic_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, list[str]]:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "scope-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Scope Test")
    _git(tmp_path, "config", "core.autocrlf", "false")
    scientific = tmp_path / "scientific.txt"
    scientific.write_bytes(b"frozen science\n")
    focus1_authority = tmp_path / "focus1-authority.json"
    focus1_authority.write_text(
        json.dumps(
            {
                "authority_commit": "1" * 40,
                "accepted_digest": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    _git(tmp_path, "add", "--", "scientific.txt", "focus1-authority.json")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "freeze")
    source_commit = _git(tmp_path, "rev-parse", "HEAD")

    support = tmp_path / "support.txt"
    support.write_bytes(b"split support\n")
    monkeypatch.setattr(scope, "SOURCE_COMMIT", source_commit)
    monkeypatch.setattr(scope, "FOCUS1_CHECKPOINT_COMMIT", "1" * 40)
    monkeypatch.setattr(scope, "ACCEPTED_FOCUS1_DIGEST", "a" * 64)
    monkeypatch.setattr(scope, "FOCUS1_AUTHORITY_RECORD_PATH", "focus1-authority.json")
    monkeypatch.setattr(scope, "IMMUTABLE_SCIENTIFIC_PATHS", ("scientific.txt",))
    monkeypatch.setattr(scope, "APPROVED_SUPPORT_PATHS", ("support.txt",))

    record = {
        "schema_version": "1.0",
        "scope_id": scope.SCOPE_ID,
        "immutable_source_commit": source_commit,
        "construction_base_commit": scope.BASE_COMMIT,
        "focus1_checkpoint_commit": "1" * 40,
        "focus1_digest_reference": "a" * 64,
        "claim_boundary": scope.CLAIM_BOUNDARY,
        "scientific_sha256": {
            "scientific.txt": hashlib.sha256(scientific.read_bytes()).hexdigest()
        },
        "split_support_paths": ["support.txt"],
    }
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    return record_path, ["scientific.txt", "support.txt"]


def _record(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_record(path: Path, record: dict[str, object]) -> None:
    path.write_text(json.dumps(record), encoding="utf-8")


def _verify(tmp_path: Path, record: Path, paths: list[str]) -> dict[str, object]:
    return scope.verify_review_scope(
        tmp_path,
        record_path=record,
        changed_paths=paths,
    )


def test_synthetic_exact_scope_passes(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record, paths = synthetic_scope
    result = _verify(tmp_path, record, paths)
    assert result["status"] == scope.VERIFIED
    assert result["expected_hash_source"] == (
        "RAW_GIT_BLOBS_AT_IMMUTABLE_OWNER_REVIEW_COMMIT"
    )
    assert result["claim_boundary"] == scope.CLAIM_BOUNDARY
    assert result["complete_focus1_or_v1_authority"] is False
    assert result["complete_sealed_study_provenance"] is False


def test_scientific_file_tampered_only_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record, paths = synthetic_scope
    (tmp_path / "scientific.txt").write_bytes(b"tampered\n")
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record, paths)
    assert raised.value.status == scope.HASH_MISMATCH


def test_recorded_hash_tampered_only_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record_path, paths = synthetic_scope
    record = _record(record_path)
    record["scientific_sha256"]["scientific.txt"] = "0" * 64
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.AUTHORITY_RECORD_HASH_MISMATCH


def test_coordinated_file_and_record_tampering_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record_path, paths = synthetic_scope
    tampered = b"coordinated tamper\n"
    (tmp_path / "scientific.txt").write_bytes(tampered)
    record = _record(record_path)
    record["scientific_sha256"]["scientific.txt"] = hashlib.sha256(tampered).hexdigest()
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.AUTHORITY_RECORD_HASH_MISMATCH


def test_missing_scientific_file_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record, paths = synthetic_scope
    (tmp_path / "scientific.txt").unlink()
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record, paths)
    assert raised.value.status == scope.FILE_MISSING


def test_unexpected_scientific_scope_path_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record_path, paths = synthetic_scope
    record = _record(record_path)
    record["scientific_sha256"]["unexpected.py"] = "0" * 64
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.PATH_SET_MISMATCH


def test_missing_scientific_scope_path_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record_path, paths = synthetic_scope
    record = _record(record_path)
    record["scientific_sha256"] = {}
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.INVALID_RECORD


def test_incorrect_focus1_digest_reference_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record_path, paths = synthetic_scope
    record = _record(record_path)
    record["focus1_digest_reference"] = "b" * 64
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.FOCUS1_REFERENCE_MISMATCH


def test_immutable_focus1_reference_mismatch_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_path, paths = synthetic_scope
    record = _record(record_path)
    monkeypatch.setattr(scope, "FOCUS1_CHECKPOINT_COMMIT", "2" * 40)
    record["focus1_checkpoint_commit"] = "2" * 40
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.FOCUS1_REFERENCE_MISMATCH


@pytest.mark.parametrize(
    "malformed",
    ["./scientific.txt", "dir//file", "dir/./file", "scientific.txt/"],
)
def test_noncanonical_path_aliases_fail(malformed: str) -> None:
    with pytest.raises(scope.ReviewScopeError) as raised:
        scope._safe_path(malformed)
    assert raised.value.status == scope.INVALID_RECORD


def test_changed_path_diff_is_replacement_neutral(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return CompletedProcess(args=args, returncode=0, stdout="scientific.txt\n")

    monkeypatch.setattr(scope.subprocess, "run", fake_run)
    assert scope._git_changed_paths(tmp_path) == ["scientific.txt"]
    assert calls == [
        [
            "git",
            "--no-replace-objects",
            "diff",
            "--name-only",
            "--no-renames",
            f"{scope.BASE_COMMIT}..HEAD",
        ]
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda record: record.update(immutable_source_commit="0" * 40),
        lambda record: record["split_support_paths"].append("support.txt"),
        lambda record: record.update(claim_boundary="COMPLETE_AUTHORITY"),
        lambda record: record.update(split_support_paths=["../support.txt"]),
    ],
)
def test_malformed_or_self_redefined_record_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
    mutation,
) -> None:
    record_path, paths = synthetic_scope
    record = _record(record_path)
    mutation(record)
    _write_record(record_path, record)
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status in {scope.INVALID_RECORD, scope.PATH_SET_MISMATCH}


def test_duplicate_json_path_key_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record_path, paths = synthetic_scope
    record_path.write_text(
        "{\"schema_version\":\"1.0\",\"schema_version\":\"1.0\"}",
        encoding="utf-8",
    )
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record_path, paths)
    assert raised.value.status == scope.INVALID_RECORD


def test_extra_or_missing_candidate_changed_path_fails(
    tmp_path: Path,
    synthetic_scope: tuple[Path, list[str]],
) -> None:
    record, paths = synthetic_scope
    with pytest.raises(scope.ReviewScopeError) as raised:
        _verify(tmp_path, record, [*paths, "unexpected.py"])
    assert raised.value.status == scope.PATH_SET_MISMATCH


def test_current_candidate_scope_verifies() -> None:
    result = scope.verify_review_scope(ROOT)
    assert result["status"] == scope.VERIFIED
    assert result["claim_boundary"] == (
        "SCIENTIFIC_SUBSET_BYTE_EQUIVALENCE_TO_IMMUTABLE_OWNER_REVIEW_SOURCE"
    )
    assert result["immutable_source_commit"] == (
        "b67bb4df0716609e3d915ec8ab4574632d43f215"
    )
    assert result["focus1_checkpoint_reference"] == (
        "124836bcc2fba48373d7bd08f0087b23f2e41620"
    )
    assert result["focus1_digest_reference"] == (
        "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
    )
    assert result["complete_focus1_or_v1_authority"] is False
    assert result["complete_sealed_study_provenance"] is False
