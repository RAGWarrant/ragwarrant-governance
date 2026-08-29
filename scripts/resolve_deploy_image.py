#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PENDING = "PENDING_FIRST_WORKFLOW_RUN"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REMEDIATION = (
    "No verified published image digest is recorded.\n"
    "Run the publish workflow, merge the digest-record PR, and make the GHCR package public before using the default image."
)


class ImageResolutionError(ValueError):
    pass


def parse_digest_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def validate_digest(value: str) -> None:
    if not value or value == PENDING:
        raise ImageResolutionError(REMEDIATION)
    if not DIGEST_RE.fullmatch(value):
        raise ImageResolutionError(f"Malformed image digest: {value}")


def validate_reference(reference: str) -> None:
    if not reference or reference == PENDING:
        raise ImageResolutionError(REMEDIATION)
    if reference.endswith(":latest") or ":latest@" in reference:
        raise ImageResolutionError("Floating latest image tags are not permitted.")
    if "@" not in reference:
        raise ImageResolutionError("Floating image tags are not permitted; use a digest-pinned image reference.")
    digest = reference.rsplit("@", 1)[1]
    validate_digest(digest)


def verify_registry_manifest(reference: str, *, platforms: str) -> None:
    expected = [item.strip() for item in platforms.split(",") if item.strip()]
    if not expected:
        return
    result = subprocess.run(["docker", "buildx", "imagetools", "inspect", reference], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ImageResolutionError("Unable to inspect image manifest through docker buildx.")
    output = result.stdout + result.stderr
    missing = [platform for platform in expected if platform not in output]
    if missing:
        raise ImageResolutionError(f"Published image manifest is missing expected platforms: {', '.join(missing)}")


def resolve_image(digest_file: Path, *, image_override: str | None = None, verify_registry: bool = False) -> str:
    if image_override is not None:
        validate_reference(image_override)
        if verify_registry:
            verify_registry_manifest(image_override, platforms="")
        return image_override
    if not digest_file.exists():
        raise ImageResolutionError(f"Missing image digest file: {digest_file}")
    values = parse_digest_file(digest_file)
    reference = values.get("REFERENCE", "")
    digest = values.get("DIGEST", "")
    validate_digest(digest)
    validate_reference(reference)
    if not reference.endswith(f"@{digest}"):
        raise ImageResolutionError("REFERENCE and DIGEST do not match.")
    if verify_registry:
        verify_registry_manifest(reference, platforms=values.get("PLATFORMS", ""))
    return reference


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve the digest-pinned RAGWarrant deployment image.")
    parser.add_argument("--digest-file", default=str(ROOT / "deploy" / "IMAGE_DIGEST"))
    parser.add_argument("--image-override", default=None)
    parser.add_argument("--verify-registry", action="store_true")
    args = parser.parse_args()
    try:
        print(resolve_image(Path(args.digest_file), image_override=args.image_override, verify_registry=args.verify_registry))
    except ImageResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
