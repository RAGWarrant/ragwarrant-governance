#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

ROOT="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && /bin/pwd)"
REPORT_DIR="${RAGWARRANT_STORAGE_EMULATOR_REPORT_DIR:-$ROOT/artifacts/storage-emulator-validation}"
S3_EMULATOR_IMAGE="localstack/localstack@sha256:fc9a03f14f4668f5d874eadb77e5da5461ce735e2ce86b77b0056606c0677dba"
AZURITE_IMAGE="mcr.microsoft.com/azure-storage/azurite@sha256:3ba0e7a70bdcc3ab1004d0d5b2cd25534a81b2785a2d0394e993dc1758512c40"
FAKE_GCS_IMAGE="fsouza/fake-gcs-server@sha256:dacee68e65c2a52cb8c4244eb2c497e956953f4981bddc5898752963d62cde35"
EMULATOR_PLATFORM="${RAGWARRANT_STORAGE_EMULATOR_PLATFORM:-linux/amd64}"

S3_EMULATOR_NAME="ragwarrant-s3-emulator-test"
AZURITE_NAME="ragwarrant-azurite-test"
FAKE_GCS_NAME="ragwarrant-fake-gcs-test"
S3_EMULATOR_PORT="${RAGWARRANT_S3_EMULATOR_PORT:-4566}"
AZURITE_PORT="${RAGWARRANT_AZURITE_PORT:-10000}"
FAKE_GCS_PORT="${RAGWARRANT_FAKE_GCS_PORT:-4443}"
AZURITE_TEST_KEY="ZmFrZUF6dXJpdGVLZXlGb3JUZXN0T25seUZha2VBenVyaXRlS2V5Rm9yVGVzdE9ubHk="

mkdir -p "$REPORT_DIR/logs"

cleanup() {
  docker logs "$S3_EMULATOR_NAME" > "$REPORT_DIR/logs/localstack-s3.log" 2>&1 || true
  docker logs "$AZURITE_NAME" > "$REPORT_DIR/logs/azurite.log" 2>&1 || true
  docker logs "$FAKE_GCS_NAME" > "$REPORT_DIR/logs/fake-gcs-server.log" 2>&1 || true
  docker rm -f "$S3_EMULATOR_NAME" "$AZURITE_NAME" "$FAKE_GCS_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for storage emulator validation." >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is required for storage emulator validation." >&2
  exit 2
fi

docker rm -f "$S3_EMULATOR_NAME" "$AZURITE_NAME" "$FAKE_GCS_NAME" >/dev/null 2>&1 || true

docker run -d --platform "$EMULATOR_PLATFORM" --name "$S3_EMULATOR_NAME" \
  -e SERVICES=s3 \
  -e DEBUG=0 \
  -p "127.0.0.1:${S3_EMULATOR_PORT}:4566" \
  "$S3_EMULATOR_IMAGE" >/dev/null

docker run -d --platform "$EMULATOR_PLATFORM" --name "$AZURITE_NAME" \
  -e "AZURITE_ACCOUNTS=devstoreaccount1:${AZURITE_TEST_KEY}" \
  -p "127.0.0.1:${AZURITE_PORT}:10000" \
  "$AZURITE_IMAGE" azurite-blob --blobHost 0.0.0.0 >/dev/null

docker run -d --platform "$EMULATOR_PLATFORM" --name "$FAKE_GCS_NAME" \
  -p "127.0.0.1:${FAKE_GCS_PORT}:4443" \
  "$FAKE_GCS_IMAGE" -scheme http -host 0.0.0.0 -port 4443 -backend memory >/dev/null

wait_for() {
  local name="$1"
  local url="$2"
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $name at $url" >&2
  return 1
}

wait_for "LocalStack S3" "http://127.0.0.1:${S3_EMULATOR_PORT}/_localstack/health"
wait_for "fake-gcs-server" "http://127.0.0.1:${FAKE_GCS_PORT}/storage/v1/b"
for _ in $(seq 1 60); do
  if curl -sS "http://127.0.0.1:${AZURITE_PORT}/devstoreaccount1?comp=list" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

export RAGWARRANT_RUN_STORAGE_EMULATOR_TESTS=1
export RAGWARRANT_S3_ENDPOINT_URL="http://127.0.0.1:${S3_EMULATOR_PORT}"
export RAGWARRANT_S3_BUCKET="ragwarrant-publication-test"
export RAGWARRANT_S3_PREFIX="public-mini"
export AWS_ACCESS_KEY_ID="emulator-access-key"
export AWS_SECRET_ACCESS_KEY="emulator-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
export RAGWARRANT_AZURE_BLOB_CONTAINER="ragwarrant-publication-test"
export RAGWARRANT_AZURE_BLOB_PREFIX="public-mini"
export RAGWARRANT_AZURE_BLOB_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=${AZURITE_TEST_KEY};BlobEndpoint=http://127.0.0.1:${AZURITE_PORT}/devstoreaccount1;"
export RAGWARRANT_GCS_BUCKET="ragwarrant-publication-test"
export RAGWARRANT_GCS_PREFIX="public-mini"
export STORAGE_EMULATOR_HOST="http://127.0.0.1:${FAKE_GCS_PORT}"

set +e
pytest -q -m storage_emulator tests/publication/test_storage_emulator_integration.py \
  --junitxml "$REPORT_DIR/pytest-storage-emulators.xml"
pytest_status=$?
set -e

python3 - "$REPORT_DIR" "$pytest_status" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
status = int(sys.argv[2])
payload = {
    "result_class": "STORAGE_EMULATOR_VALIDATION_PASSED" if status == 0 else "STORAGE_EMULATOR_VALIDATION_FAILED",
    "pytest_exit_code": status,
    "emulators": {
        "s3": "protocol_tested",
        "azurite": "protocol_tested",
        "fake_gcs_server": "protocol_tested",
    },
    "raw_payloads_exported": False,
    "secrets_exported": False,
    "private_paths_exported": False,
}
(report_dir / "storage_emulator_validation_report.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(report_dir / "storage_emulator_validation_report.md").write_text(
    "# Storage Emulator Validation\n\n"
    f"Result: `{payload['result_class']}`.\n\n"
    "LocalStack S3, Azurite, and fake-gcs-server use pinned image digests and protocol-compatible SDK paths.\n",
    encoding="utf-8",
)
PY

exit "$pytest_status"
