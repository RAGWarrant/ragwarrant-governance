#!/usr/bin/env bash
set -euo pipefail
ragwarrant run-governance-job \
  --config "${RAGWARRANT_JOB_CONFIG:-configs/jobs/public_mini_governance_job.yaml}" \
  --output-root "${RAGWARRANT_OUTPUT_ROOT:-/outputs}" \
  --decision-out "${RAGWARRANT_DECISION_OUT:-/outputs/promotion_decision.json}"
