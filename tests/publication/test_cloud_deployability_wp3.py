from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_publish_container_workflow_has_supply_chain_controls() -> None:
    text = (ROOT / ".github" / "workflows" / "publish-container.yml").read_text(encoding="utf-8")
    assert "platforms: linux/amd64,linux/arm64" in text
    assert "provenance: mode=max" in text
    assert "sbom: true" in text
    assert "cosign sign --yes" in text
    assert "ghcr.io/ragwarrant/ragwarrant-governance" in text
    assert ":latest" not in text
    assert "push:" in text
    assert "tags:" in text
    assert '"v*"' in text
    assert "docker buildx imagetools inspect" in text
    assert "digest-record/${GITHUB_RUN_ID}" in text
    assert "gh pr create" in text
    assert "deploy/IMAGE_DIGEST" in text


def test_image_digest_file_is_pending_or_real_digest() -> None:
    text = (ROOT / "deploy" / "IMAGE_DIGEST").read_text(encoding="utf-8")
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    assert fields["IMAGE"] == "ghcr.io/ragwarrant/ragwarrant-governance"
    assert fields["REAL_CLOUD_DEPLOYMENT_PERFORMED"] == "false"
    digest = fields["DIGEST"]
    assert digest == "PENDING_FIRST_WORKFLOW_RUN" or re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert re.fullmatch(r"[0-9a-f]{64}", fields["BUILD_INPUT_SHA256"])


def test_build_input_hash_is_stable_and_nonempty() -> None:
    first = subprocess.check_output([sys.executable, "scripts/compute_container_build_input_hash.py"], cwd=ROOT, text=True).strip()
    second = subprocess.check_output([sys.executable, "scripts/compute_container_build_input_hash.py"], cwd=ROOT, text=True).strip()
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)


def test_record_image_digest_rejects_non_digest(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/record_image_digest.py",
            "--digest",
            "not-a-digest",
            "--build-input-sha256",
            "0" * 64,
            "--output",
            str(tmp_path / "IMAGE_DIGEST"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (tmp_path / "IMAGE_DIGEST").exists()


def test_resolve_deploy_image_blocks_pending_sentinel(tmp_path: Path) -> None:
    digest_file = tmp_path / "IMAGE_DIGEST"
    digest_file.write_text(
        "IMAGE=ghcr.io/ragwarrant/ragwarrant-governance\n"
        "REFERENCE=PENDING_FIRST_WORKFLOW_RUN\n"
        "DIGEST=PENDING_FIRST_WORKFLOW_RUN\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "scripts/resolve_deploy_image.py", "--digest-file", str(digest_file)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Run the publish workflow" in result.stderr
    assert "merge the digest-record PR" in result.stderr
    assert "make the GHCR package public" in result.stderr


def test_resolve_deploy_image_accepts_valid_digest_fixture(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    digest_file = tmp_path / "IMAGE_DIGEST"
    digest_file.write_text(
        "IMAGE=ghcr.io/ragwarrant/ragwarrant-governance\n"
        f"REFERENCE=ghcr.io/ragwarrant/ragwarrant-governance@{digest}\n"
        f"DIGEST={digest}\n"
        "PLATFORMS=linux/amd64,linux/arm64\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "scripts/resolve_deploy_image.py", "--digest-file", str(digest_file)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"ghcr.io/ragwarrant/ragwarrant-governance@{digest}"


@pytest.mark.parametrize(
    "reference",
    [
        "ghcr.io/ragwarrant/ragwarrant-governance:latest",
        "ghcr.io/ragwarrant/ragwarrant-governance:main",
        "",
        "ghcr.io/ragwarrant/ragwarrant-governance@sha256:nothex",
    ],
)
def test_resolve_deploy_image_rejects_malformed_or_floating_overrides(reference: str) -> None:
    command = [sys.executable, "scripts/resolve_deploy_image.py", "--image-override", reference]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 2


def test_deploy_templates_do_not_embed_pending_sentinel() -> None:
    offenders = []
    for path in (ROOT / "deploy").rglob("*"):
        if path.is_file() and path.name != "IMAGE_DIGEST" and "PENDING_FIRST_WORKFLOW_RUN" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
