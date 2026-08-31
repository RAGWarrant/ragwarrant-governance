from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ragwarrant.research import packaging_portability_amendment as authority


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_focus1_authority.py"


def _git(
    repository: Path,
    *arguments: str,
    check: bool = True,
    text: bool = True,
    input_value: str | bytes | None = None,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=check,
        capture_output=True,
        text=text,
        input=input_value,
    )


def _write(repository: Path, relative_path: str, content: str) -> None:
    path = repository.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", "--all")
    _git(repository, "commit", "-q", "-m", message)
    return _git(repository, "rev-parse", "HEAD").stdout.strip()


@dataclass(frozen=True)
class SyntheticAuthorityGraph:
    repository: Path
    main_commit: str
    checkpoint_commit: str
    candidate_commit: str
    frozen_paths: tuple[str, ...]
    expected_hashes: dict[str, str]
    accepted_digest: str
    lineage_record: dict[str, Any]
    detached_record: dict[str, Any]


@pytest.fixture
def synthetic_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SyntheticAuthorityGraph:
    repository = tmp_path / "authority-repository"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    _git(repository, "config", "user.email", "authority@example.invalid")
    _git(repository, "config", "user.name", "Detached Authority Test")
    _write(repository, "README.md", "current main baseline\n")
    main_commit = _commit(repository, "current main baseline")

    _git(repository, "switch", "--orphan", "historical-focus1")
    frozen_paths = (
        "configs/research/false_promotion_benchmark_v1.yaml",
        "docs/research/frozen_protocol.md",
        "scripts/generate_benchmark_freeze_manifest.py",
        "src/ragwarrant/research/public_beacon.py",
    )
    generator = "FROZEN_PATHS = (\n" + "".join(
        f"    {path!r},\n" for path in frozen_paths
    ) + ")\n"
    frozen_content = {
        frozen_paths[0]: (
            "protocol_version: synthetic_false_promotion_v1\n"
            "seed_schedule_version: 2\n"
        ),
        frozen_paths[1]: "Synthetic test-only frozen protocol.\n",
        frozen_paths[2]: generator,
        frozen_paths[3]: 'FULL_ENTROPY_PROTOCOL = "SYNTHETIC_TEST_ONLY"\n',
    }
    for path, content in frozen_content.items():
        _write(repository, path, content)
    checkpoint_commit = _commit(repository, "historical Focus 1 checkpoint")
    _git(
        repository,
        "tag",
        "-a",
        authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/"),
        "-m",
        "synthetic annotated authority",
        checkpoint_commit,
    )

    expected_hashes = {
        path: hashlib.sha256(
            _git(
                repository,
                "--no-replace-objects",
                "cat-file",
                "blob",
                f"{checkpoint_commit}:{path}",
                text=False,
            ).stdout
        ).hexdigest()
        for path in frozen_paths
    }
    manifest = authority._focus1_manifest_payload(
        benchmark_protocol_version="synthetic_false_promotion_v1",
        seed_schedule_version=2,
        full_entropy_protocol="SYNTHETIC_TEST_ONLY",
        input_hashes=expected_hashes,
    )
    accepted_digest = authority._focus1_digest(manifest)
    monkeypatch.setattr(authority, "FOCUS1_CHECKPOINT_COMMIT", checkpoint_commit)
    monkeypatch.setattr(authority, "FOCUS1_CHECKPOINT_INPUT_SHA256", expected_hashes)
    monkeypatch.setattr(authority, "FOCUS1_DIGEST", accepted_digest)

    _git(repository, "switch", "main")
    for path, content in frozen_content.items():
        _write(repository, path, content)
    candidate_commit = _commit(repository, "replay Focus 1 onto current main")

    lineage_record = authority._lineage_authority_record()
    detached_record = copy.deepcopy(lineage_record)
    detached_record.update(
        {
            "authority_mode": authority.DETACHED_PINNED_CHECKPOINT,
            "authority_ref": authority.FOCUS1_AUTHORITY_REF,
            "lineage_required": False,
        }
    )
    return SyntheticAuthorityGraph(
        repository=repository,
        main_commit=main_commit,
        checkpoint_commit=checkpoint_commit,
        candidate_commit=candidate_commit,
        frozen_paths=frozen_paths,
        expected_hashes=expected_hashes,
        accepted_digest=accepted_digest,
        lineage_record=lineage_record,
        detached_record=detached_record,
    )


def _verify(
    graph: SyntheticAuthorityGraph,
    record: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return authority._verify_focus1_authority_contract(
        graph.repository,
        record or graph.detached_record,
        **kwargs,
    )


def test_true_lineage_checkpoint_passes_lineage_mode(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    _git(synthetic_graph.repository, "switch", "historical-focus1")
    result = _verify(synthetic_graph, synthetic_graph.lineage_record)
    assert result["status"] == authority.FOCUS1_AUTHORITY_VERIFIED_LINEAGE
    assert result["observed_digest"] == synthetic_graph.accepted_digest


def test_detached_checkpoint_fails_lineage_mode(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph, synthetic_graph.lineage_record)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_UNTRUSTED_SOURCE


def test_exact_annotated_tag_passes_detached_mode(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    result = _verify(synthetic_graph)
    assert result["status"] == authority.FOCUS1_AUTHORITY_VERIFIED_DETACHED
    assert result["candidate_commit"] == synthetic_graph.candidate_commit
    assert result["observed_digest"] == synthetic_graph.accepted_digest


def test_same_content_replayed_to_unrelated_baseline_passes_without_bridge(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    result = _verify(synthetic_graph)
    assert result["lineage_required"] is False
    for historical in (
        synthetic_graph.checkpoint_commit,
        synthetic_graph.main_commit,
    ):
        expected = 0 if historical == synthetic_graph.main_commit else 1
        ancestry = _git(
            synthetic_graph.repository,
            "merge-base",
            "--is-ancestor",
            historical,
            synthetic_graph.candidate_commit,
            check=False,
        )
        assert ancestry.returncode == expected
    merges = _git(
        synthetic_graph.repository,
        "rev-list",
        "--min-parents=2",
        f"{synthetic_graph.main_commit}..{synthetic_graph.candidate_commit}",
    ).stdout.splitlines()
    assert merges == []


def test_missing_authority_tag_fails(synthetic_graph: SyntheticAuthorityGraph) -> None:
    _git(
        synthetic_graph.repository,
        "tag",
        "-d",
        authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/"),
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_TAG_MISSING


def test_detached_missing_tag_does_not_fallback_to_valid_lineage(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    _git(synthetic_graph.repository, "switch", "historical-focus1")
    _git(
        synthetic_graph.repository,
        "tag",
        "-d",
        authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/"),
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_TAG_MISSING


def test_lightweight_tag_fails(synthetic_graph: SyntheticAuthorityGraph) -> None:
    tag_name = authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/")
    _git(synthetic_graph.repository, "tag", "-d", tag_name)
    _git(synthetic_graph.repository, "tag", tag_name, synthetic_graph.checkpoint_commit)
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_TAG_NOT_ANNOTATED


def test_tag_retargeted_to_another_commit_fails(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    tag_name = authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/")
    _git(synthetic_graph.repository, "tag", "-d", tag_name)
    _git(
        synthetic_graph.repository,
        "tag",
        "-a",
        tag_name,
        "-m",
        "retargeted",
        synthetic_graph.candidate_commit,
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_TAG_TARGET_MISMATCH


@pytest.mark.parametrize("target_kind", ["tree", "blob"])
def test_tag_pointing_to_noncommit_fails(
    synthetic_graph: SyntheticAuthorityGraph,
    target_kind: str,
) -> None:
    tag_name = authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/")
    object_expression = (
        f"{synthetic_graph.checkpoint_commit}^{{tree}}"
        if target_kind == "tree"
        else f"{synthetic_graph.checkpoint_commit}:{synthetic_graph.frozen_paths[1]}"
    )
    target = _git(
        synthetic_graph.repository, "rev-parse", object_expression
    ).stdout.strip()
    _git(synthetic_graph.repository, "tag", "-d", tag_name)
    _git(
        synthetic_graph.repository,
        "tag",
        "-a",
        tag_name,
        "-m",
        f"invalid {target_kind} target",
        target,
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID


def test_tag_of_tag_fails(synthetic_graph: SyntheticAuthorityGraph) -> None:
    tag_name = authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/")
    _git(
        synthetic_graph.repository,
        "tag",
        "-a",
        "inner-authority",
        "-m",
        "inner",
        synthetic_graph.checkpoint_commit,
    )
    _git(synthetic_graph.repository, "tag", "-d", tag_name)
    _git(
        synthetic_graph.repository,
        "tag",
        "-a",
        tag_name,
        "-m",
        "outer",
        "inner-authority",
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID


def test_dangling_annotated_tag_reports_missing_commit(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = "0" * 40
    raw_tag = (
        f"object {missing}\n"
        "type commit\n"
        f"tag {authority.FOCUS1_AUTHORITY_REF.removeprefix('refs/tags/')}\n"
        "tagger Synthetic <synthetic@example.invalid> 0 +0000\n\n"
        "dangling synthetic tag\n"
    )
    tag_object = _git(
        synthetic_graph.repository,
        "hash-object",
        "--literally",
        "-t",
        "tag",
        "-w",
        "--stdin",
        input_value=raw_tag,
    ).stdout.strip()
    _git(
        synthetic_graph.repository,
        "tag",
        "-d",
        authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/"),
    )
    loose_ref = synthetic_graph.repository / ".git" / Path(
        *authority.FOCUS1_AUTHORITY_REF.split("/")
    )
    loose_ref.parent.mkdir(parents=True, exist_ok=True)
    loose_ref.write_text(tag_object + "\n", encoding="ascii")
    monkeypatch.setattr(authority, "FOCUS1_CHECKPOINT_COMMIT", missing)
    record = copy.deepcopy(synthetic_graph.detached_record)
    record["authority_commit"] = missing
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph, record)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_COMMIT_MISSING


def test_shallow_checkout_without_tag_fails_clearly(
    synthetic_graph: SyntheticAuthorityGraph,
    tmp_path: Path,
) -> None:
    shallow = tmp_path / "shallow"
    _git(
        tmp_path,
        "clone",
        "-q",
        "--depth",
        "1",
        "--no-tags",
        "--branch",
        "main",
        synthetic_graph.repository.as_uri(),
        str(shallow),
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        authority._verify_focus1_authority_contract(
            shallow,
            synthetic_graph.detached_record,
        )
    assert caught.value.status == authority.FOCUS1_AUTHORITY_TAG_MISSING


def test_committed_candidate_tamper_fails_even_if_worktree_is_repaired(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    target = synthetic_graph.frozen_paths[1]
    original = _git(
        synthetic_graph.repository,
        "show",
        f"{synthetic_graph.checkpoint_commit}:{target}",
    ).stdout
    _write(synthetic_graph.repository, target, "tampered candidate commit\n")
    _commit(synthetic_graph.repository, "tamper candidate frozen file")
    _write(synthetic_graph.repository, target, original)
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_CANDIDATE_BLOB_MISMATCH


def test_missing_candidate_frozen_file_fails(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    target = synthetic_graph.frozen_paths[1]
    _git(synthetic_graph.repository, "rm", "-q", "--", target)
    _commit(synthetic_graph.repository, "remove candidate frozen file")
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH


def test_extra_observed_path_fails(synthetic_graph: SyntheticAuthorityGraph) -> None:
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(
            synthetic_graph,
            observed_paths=(*synthetic_graph.frozen_paths, "extra/frozen.py"),
        )
    assert caught.value.status == authority.FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH


def test_changed_accepted_digest_fails_checkpoint_reproduction(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed = "f" * 64
    monkeypatch.setattr(authority, "FOCUS1_DIGEST", changed)
    record = copy.deepcopy(synthetic_graph.detached_record)
    record["accepted_digest"] = changed
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph, record)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH


def test_different_checkpoint_bytes_fail_accepted_inventory(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git(synthetic_graph.repository, "switch", "historical-focus1")
    _write(
        synthetic_graph.repository,
        synthetic_graph.frozen_paths[1],
        "different historical bytes\n",
    )
    changed_checkpoint = _commit(synthetic_graph.repository, "different checkpoint")
    tag_name = authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/")
    _git(synthetic_graph.repository, "tag", "-d", tag_name)
    _git(
        synthetic_graph.repository,
        "tag",
        "-a",
        tag_name,
        "-m",
        "changed checkpoint",
        changed_checkpoint,
    )
    _git(synthetic_graph.repository, "switch", "main")
    monkeypatch.setattr(authority, "FOCUS1_CHECKPOINT_COMMIT", changed_checkpoint)
    record = copy.deepcopy(synthetic_graph.detached_record)
    record["authority_commit"] = changed_checkpoint
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph, record)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH


def test_replace_ref_is_rejected(synthetic_graph: SyntheticAuthorityGraph) -> None:
    _git(
        synthetic_graph.repository,
        "replace",
        synthetic_graph.checkpoint_commit,
        synthetic_graph.candidate_commit,
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_REPLACE_OBJECT_REJECTED


def test_legacy_graft_is_rejected(synthetic_graph: SyntheticAuthorityGraph) -> None:
    common_dir = Path(
        _git(synthetic_graph.repository, "rev-parse", "--git-common-dir").stdout.strip()
    )
    if not common_dir.is_absolute():
        common_dir = synthetic_graph.repository / common_dir
    grafts = common_dir / "info" / "grafts"
    grafts.parent.mkdir(parents=True, exist_ok=True)
    grafts.write_text(
        f"{synthetic_graph.candidate_commit} {synthetic_graph.checkpoint_commit}\n",
        encoding="ascii",
    )
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_REPLACE_OBJECT_REJECTED


def test_authority_ref_alias_is_rejected(
    synthetic_graph: SyntheticAuthorityGraph,
) -> None:
    record = copy.deepcopy(synthetic_graph.detached_record)
    record["authority_ref"] = authority.FOCUS1_AUTHORITY_REF.removeprefix("refs/tags/")
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph, record)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_MODE_INVALID


def test_unknown_mode_fails_closed(synthetic_graph: SyntheticAuthorityGraph) -> None:
    record = copy.deepcopy(synthetic_graph.detached_record)
    record["authority_mode"] = "AUTOMATIC_FALLBACK"
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph, record)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_MODE_INVALID


def test_detached_mode_never_calls_merge_base(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run = authority._git_no_replace
    calls: list[tuple[str, ...]] = []

    def recording_run(
        repository_root: Path,
        arguments: tuple[str, ...] | list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        calls.append(tuple(arguments))
        return real_run(repository_root, arguments, **kwargs)

    monkeypatch.setattr(authority, "_git_no_replace", recording_run)
    assert _verify(synthetic_graph)["status"] == authority.FOCUS1_AUTHORITY_VERIFIED_DETACHED
    assert not any(call[:1] == ("merge-base",) for call in calls)


def test_candidate_digest_is_computed_independently(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_digest = authority._focus1_digest
    digest_calls = 0

    def candidate_divergence(payload: dict[str, Any]) -> str:
        nonlocal digest_calls
        digest_calls += 1
        computed = real_digest(payload)
        return "e" * 64 if digest_calls == 2 else computed

    monkeypatch.setattr(authority, "_focus1_digest", candidate_divergence)
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_CANDIDATE_DIGEST_MISMATCH
    assert digest_calls == 2


def test_inherited_git_redirection_environment_is_ignored(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_DIR", str(synthetic_graph.repository / "missing-git-dir"))
    monkeypatch.setenv("GIT_WORK_TREE", str(synthetic_graph.repository / "missing-tree"))
    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/evil/")
    result = _verify(synthetic_graph)
    assert result["status"] == authority.FOCUS1_AUTHORITY_VERIFIED_DETACHED


def test_ref_retarget_during_verification_is_detected(
    synthetic_graph: SyntheticAuthorityGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run = authority._git_no_replace
    show_ref_calls = 0

    def racing_run(
        repository_root: Path,
        arguments: tuple[str, ...] | list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        nonlocal show_ref_calls
        result = real_run(repository_root, arguments, **kwargs)
        if tuple(arguments)[:1] == ("show-ref",):
            show_ref_calls += 1
            if show_ref_calls == 2:
                return subprocess.CompletedProcess(
                    result.args,
                    0,
                    stdout="f" * 40 + "\n",
                    stderr="",
                )
        return result

    monkeypatch.setattr(authority, "_git_no_replace", racing_run)
    with pytest.raises(authority.PortabilityVerificationError) as caught:
        _verify(synthetic_graph)
    assert caught.value.status == authority.FOCUS1_AUTHORITY_TAG_TARGET_MISMATCH


def test_repository_record_and_cli_emit_detached_verified_status() -> None:
    direct = authority.verify_focus1_authority(ROOT)
    assert direct["status"] == authority.FOCUS1_AUTHORITY_VERIFIED_DETACHED
    completed = subprocess.run(
        [os.fspath(Path(os.sys.executable)), os.fspath(SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == authority.FOCUS1_AUTHORITY_VERIFIED_DETACHED
    assert payload["observed_digest"] == authority.FOCUS1_DIGEST
