#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="${1:-$ROOT/../publication_bundle_output/ragwarrant-governance_$STAMP}"

mkdir -p "$OUT/repository_bundle" "$OUT/approval_package" "$OUT/validation_reports" "$OUT/manifests" "$OUT/excluded" "$OUT/checksums" "$OUT/archives"
rsync -a --delete --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' --exclude='.pytest_cache/' --exclude='.ruff_cache/' "$ROOT/" "$OUT/repository_bundle/"

EXPORT_ROOT="$OUT" python "$OUT/repository_bundle/scripts/validate_publication_bundle.py"

tar -czf "$OUT/archives/ragwarrant-governance_publication_bundle_$STAMP.tar.gz" -C "$OUT" repository_bundle
tar -czf "$OUT/archives/ragwarrant-governance_approval_package_$STAMP.tar.gz" -C "$OUT" approval_package validation_reports manifests checksums excluded README_EXPORT.md

find "$OUT" -type f -not -path '*/archives/*' -print0 | xargs -0 shasum -a 256 > "$OUT/checksums/file_checksums.sha256"
shasum -a 256 "$OUT"/archives/*.tar.gz > "$OUT/checksums/archive_checksums.sha256"

echo "$OUT"
