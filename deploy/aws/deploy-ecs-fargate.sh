#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
image_ref="$(deploy/load-image-reference.sh)"
tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT
sed "s#RAGWARRANT_IMAGE_REFERENCE_PLACEHOLDER#$image_ref#g" \
  deploy/aws/ecs-fargate-task.json > "$tmp_file"
aws ecs register-task-definition --cli-input-json "file://$tmp_file"
