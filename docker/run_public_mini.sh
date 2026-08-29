#!/usr/bin/env bash
set -euo pipefail
ragwarrant run-public-mini --output-root "${RAGWARRANT_OUTPUT_ROOT:-/outputs/public_mini_reproduction}" --force
