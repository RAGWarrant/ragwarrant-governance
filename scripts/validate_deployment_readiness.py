#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.deployment_readiness import validate_deployment_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RAGWarrant deployment-readiness assets")
    parser.add_argument("--config", default="configs/experiments/ragwarrant_deployment_readiness_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/deployment_readiness")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = validate_deployment_readiness(ROOT, output_root=ROOT / args.output_root, config_path=ROOT / args.config)
    print(json.dumps({"result_class": manifest["result_class"], "cloud_templates_ready": manifest["cloud_templates_ready"]}, sort_keys=True))
    return 0 if manifest["result_class"] != "DEPLOYMENT_READINESS_BLOCKED_PUBLICATION_HYGIENE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
