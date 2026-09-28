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

from ragwarrant.generative_validation_common import write_json, write_md
from ragwarrant.mounted_job_contract import check_mounted_job_contract, exercise_storage_mode


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the RAGWarrant mounted governance-job I/O contract.")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--write-probe", action="store_true")
    parser.add_argument("--storage-mode", action="append", default=["local", "s3", "azure_blob", "gcs"])
    args = parser.parse_args()
    output_root = Path(args.output_root) if args.output_root else None
    status, contract = check_mounted_job_contract(write_probe=args.write_probe, output_root=output_root)
    report_root = output_root or Path(".")
    report_root.mkdir(parents=True, exist_ok=True)
    storage = [exercise_storage_mode(mode, output_root=report_root / "storage_probe") for mode in args.storage_mode]
    payload = {
        "contract_status": "passed" if status == 0 else "fallback",
        "exit_code": status,
        "contract": contract,
        "storage_modes": storage,
        "real_cloud_deployment_performed": False,
        "raw_text_exported": False,
        "private_paths_exported": False,
        "secrets_exported": False,
    }
    write_json(report_root / "mounted_job_contract_full_report.json", payload)
    lines = [
        "# Mounted Governance-Job Contract Check",
        "",
        f"Contract status: `{payload['contract_status']}`",
        f"Input dir exists: `{contract['input_dir_exists']}`",
        f"Output dir writable: `{contract['output_dir_writable']}`",
        "",
        "Storage modes:",
    ]
    for item in storage:
        status_text = "available" if item["available"] else item["fallback"]
        lines.append(f"- `{item['mode']}`: `{status_text}`")
    lines.append("")
    lines.append("No raw text, private paths, secrets, or real cloud resources are exported by this check.")
    write_md(report_root / "mounted_job_contract_full_report.md", "\n".join(lines) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
