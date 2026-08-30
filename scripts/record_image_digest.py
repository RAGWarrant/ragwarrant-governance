#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PENDING = "PENDING_FIRST_WORKFLOW_RUN"


def _validate_digest(value: str) -> None:
    if value == PENDING:
        return
    if not SHA256_RE.fullmatch(value):
        raise SystemExit(f"invalid image digest: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the published RAGWarrant image digest.")
    parser.add_argument("--image", default="ghcr.io/ragwarrant/ragwarrant-governance")
    parser.add_argument("--digest", required=True)
    parser.add_argument("--candidate-tag", default=PENDING)
    parser.add_argument("--source-commit", default=PENDING)
    parser.add_argument("--build-input-sha256", required=True)
    parser.add_argument("--platforms", default="linux/amd64,linux/arm64")
    parser.add_argument("--output", default="deploy/IMAGE_DIGEST")
    args = parser.parse_args()
    _validate_digest(args.digest)
    reference = PENDING if args.digest == PENDING else f"{args.image}@{args.digest}"
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"IMAGE={args.image}",
                f"REFERENCE={reference}",
                f"DIGEST={args.digest}",
                f"CANDIDATE_TAG={args.candidate_tag}",
                f"SOURCE_COMMIT={args.source_commit}",
                f"BUILD_INPUT_SHA256={args.build_input_sha256}",
                f"PLATFORMS={args.platforms}",
                "REAL_CLOUD_DEPLOYMENT_PERFORMED=false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

