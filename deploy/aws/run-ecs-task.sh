#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
"$(dirname "$0")/../load-image-reference.sh" >/dev/null
: "${RAGWARRANT_AWS_CLUSTER:?set RAGWARRANT_AWS_CLUSTER}"
: "${RAGWARRANT_AWS_SUBNET:?set RAGWARRANT_AWS_SUBNET}"
: "${RAGWARRANT_AWS_SECURITY_GROUP:?set RAGWARRANT_AWS_SECURITY_GROUP}"
aws ecs run-task \
  --cluster "$RAGWARRANT_AWS_CLUSTER" \
  --launch-type FARGATE \
  --task-definition ragwarrant-governance-task \
  --network-configuration "awsvpcConfiguration={subnets=[$RAGWARRANT_AWS_SUBNET],securityGroups=[$RAGWARRANT_AWS_SECURITY_GROUP],assignPublicIp=DISABLED}"
