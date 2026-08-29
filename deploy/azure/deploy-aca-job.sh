#!/usr/bin/env bash
set -euo pipefail
: "${RAGWARRANT_AZURE_RESOURCE_GROUP:?set RAGWARRANT_AZURE_RESOURCE_GROUP}"
image_ref="$(deploy/load-image-reference.sh)"
az deployment group create \
  --resource-group "$RAGWARRANT_AZURE_RESOURCE_GROUP" \
  --template-file deploy/azure/container-apps-job.bicep \
  --parameters image="$image_ref"
