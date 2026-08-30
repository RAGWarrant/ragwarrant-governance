#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/../load-image-reference.sh" >/dev/null
: "${RAGWARRANT_AWS_BATCH_QUEUE:?set RAGWARRANT_AWS_BATCH_QUEUE}"
aws batch submit-job \
  --job-name ragwarrant-governance-job \
  --job-queue "$RAGWARRANT_AWS_BATCH_QUEUE" \
  --job-definition ragwarrant-governance-batch
