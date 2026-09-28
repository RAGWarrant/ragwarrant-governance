#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
: "${RAGWARRANT_GCP_REGION:?set RAGWARRANT_GCP_REGION}"
image_ref="$(deploy/load-image-reference.sh)"
tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT
sed "s#RAGWARRANT_IMAGE_REFERENCE_PLACEHOLDER#$image_ref#g" \
  deploy/gcp/cloud-run-job.yaml > "$tmp_file"
gcloud run jobs replace "$tmp_file" --region "$RAGWARRANT_GCP_REGION"
