#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
"$(dirname "$0")/../load-image-reference.sh" >/dev/null
: "${RAGWARRANT_GCP_REGION:?set RAGWARRANT_GCP_REGION}"
gcloud run jobs execute ragwarrant-governance-job --region "$RAGWARRANT_GCP_REGION" --wait
