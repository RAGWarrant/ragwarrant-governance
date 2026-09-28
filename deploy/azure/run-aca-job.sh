#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
"$(dirname "$0")/../load-image-reference.sh" >/dev/null
: "${RAGWARRANT_AZURE_RESOURCE_GROUP:?set RAGWARRANT_AZURE_RESOURCE_GROUP}"
: "${RAGWARRANT_AZURE_JOB_NAME:=ragwarrant-governance-job}"
az containerapp job start --resource-group "$RAGWARRANT_AZURE_RESOURCE_GROUP" --name "$RAGWARRANT_AZURE_JOB_NAME"
