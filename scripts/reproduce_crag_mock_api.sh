#!/usr/bin/env bash
set -euo pipefail

CRAG_RAW_DIR="${CRAG_RAW_DIR:-/data/crag/raw}"

if [ ! -d "$CRAG_RAW_DIR" ]; then
  echo "CRAG raw data not found at $CRAG_RAW_DIR."
  echo "Obtain CRAG from the original provider under the approved noncommercial restriction."
  echo "Then rerun with CRAG_RAW_DIR=/path/to/crag/raw."
  exit 2
fi

echo "CRAG raw data directory found: $CRAG_RAW_DIR"
echo "Run the source-suite command appropriate for your checkout:"
echo "python -m ragwarrant.cli run-suite --suite ragwarrant_crag_mock_api_validation_v1 --config configs/experiments/ragwarrant_crag_mock_api_validation_v1.yaml --output-dir artifacts/ragwarrant/runs --run-id auto"
