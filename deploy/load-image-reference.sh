#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
digest_file="${RAGWARRANT_IMAGE_DIGEST_FILE:-$repo_root/deploy/IMAGE_DIGEST}"

args=(python3 "$repo_root/scripts/resolve_deploy_image.py" --digest-file "$digest_file")
if [[ -n "${RAGWARRANT_IMAGE_REFERENCE:-}" ]]; then
  args+=(--image-override "$RAGWARRANT_IMAGE_REFERENCE")
fi
exec "${args[@]}"
