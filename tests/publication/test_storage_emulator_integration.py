# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


pytestmark = pytest.mark.storage_emulator


def _require_emulators() -> None:
    if os.environ.get("RAGWARRANT_RUN_STORAGE_EMULATOR_TESTS") != "1":
        pytest.skip("storage emulator integration tests require scripts/run_storage_emulator_tests.sh")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def _run_staged_job(mode: str, output_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/run_storage_staging_job.py",
            "--mode",
            mode,
            "--output-root",
            str(output_root),
            "--",
            sys.executable,
            "-m",
            "ragwarrant.cli",
            "run-governance-job",
            "--config",
            "configs/jobs/public_mini_governance_job.yaml",
            "--output-root",
            str(output_root),
            "--decision-out",
            str(output_root / "promotion_decision.json"),
        ],
        cwd=ROOT,
        env=_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_decision(output_root: Path) -> None:
    decision = json.loads((output_root / "promotion_decision.json").read_text(encoding="utf-8"))
    assert decision["result_class"] == "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED"
    assert decision["decision"] == "BLOCK"
    report = json.loads((output_root / "storage_staging_report.json").read_text(encoding="utf-8"))
    assert report["wrapped_exit_code"] == 0
    assert any(item["local_path"] == "promotion_decision.json" for item in report["staged_artifacts"])


def _s3_has_decision() -> bool:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["RAGWARRANT_S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )
    response = client.list_objects_v2(Bucket=os.environ["RAGWARRANT_S3_BUCKET"], Prefix=os.environ["RAGWARRANT_S3_PREFIX"])
    return any(item["Key"].endswith("promotion_decision.json") for item in response.get("Contents", []))


def _azure_has_decision() -> bool:
    from azure.storage.blob import BlobServiceClient

    client = BlobServiceClient.from_connection_string(os.environ["RAGWARRANT_AZURE_BLOB_CONNECTION_STRING"])
    blobs = client.get_container_client(os.environ["RAGWARRANT_AZURE_BLOB_CONTAINER"]).list_blobs(
        name_starts_with=os.environ["RAGWARRANT_AZURE_BLOB_PREFIX"]
    )
    return any(blob.name.endswith("promotion_decision.json") for blob in blobs)


def _gcs_has_decision() -> bool:
    from google.cloud import storage

    client = storage.Client.create_anonymous_client()
    blobs = client.list_blobs(os.environ["RAGWARRANT_GCS_BUCKET"], prefix=os.environ["RAGWARRANT_GCS_PREFIX"])
    return any(blob.name.endswith("promotion_decision.json") for blob in blobs)


@pytest.mark.parametrize(
    ("mode", "remote_check"),
    [
        ("s3", _s3_has_decision),
        ("azure_blob", _azure_has_decision),
        ("gcs", _gcs_has_decision),
    ],
)
def test_storage_emulator_stages_public_mini_outputs(mode: str, remote_check, tmp_path: Path) -> None:
    _require_emulators()
    output_root = tmp_path / mode / "success"
    result = _run_staged_job(mode, output_root)
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_decision(output_root)
    assert remote_check() is True


@pytest.mark.parametrize("mode", ["s3", "azure_blob", "gcs"])
def test_storage_staging_preserves_wrapped_failure_exit_code(mode: str, tmp_path: Path) -> None:
    _require_emulators()
    output_root = tmp_path / mode / "failure"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_storage_staging_job.py",
            "--mode",
            mode,
            "--output-root",
            str(output_root),
            "--",
            sys.executable,
            "-c",
            "import os, pathlib, sys; root=pathlib.Path(os.environ['RAGWARRANT_OUTPUT_DIR']); root.mkdir(parents=True, exist_ok=True); (root/'controlled_failure.json').write_text('{\"status\":\"failed\"}\\n', encoding='utf-8'); sys.exit(7)",
        ],
        cwd=ROOT,
        env=_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 7
    report = json.loads((output_root / "storage_staging_report.json").read_text(encoding="utf-8"))
    assert report["wrapped_exit_code"] == 7
    assert any(item["local_path"] == "controlled_failure.json" for item in report["staged_artifacts"])
