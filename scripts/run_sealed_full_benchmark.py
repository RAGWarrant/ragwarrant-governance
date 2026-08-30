from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ragwarrant.research.benchmark import run_benchmark
from ragwarrant.research.public_beacon import (
    verified_full_entropy_from_receipt,
    verify_benchmark_freeze_manifest,
)
from ragwarrant.research.reporting import write_benchmark_outputs
from ragwarrant.research.simulator import load_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
PINNED_VERIFIER = REPOSITORY_ROOT / ".github/drand-verifier/verify_quicknet.mjs"
PINNED_VERIFIER_PACKAGE = REPOSITORY_ROOT / ".github/drand-verifier/node_modules/drand-client/package.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run FULL only from one public, verified, frozen future-round seal."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--seal-publication", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _file_hashes(paths: list[Path]) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths, key=lambda item: item.name)
    }


def _invoke_pinned_verifier(seal: Path, publication: Path, receipt: Path) -> None:
    if not PINNED_VERIFIER.is_file() or not PINNED_VERIFIER_PACKAGE.is_file():
        raise SystemExit(
            "pinned drand verifier is not installed; run npm ci from .github/drand-verifier"
        )
    package = json.loads(PINNED_VERIFIER_PACKAGE.read_text(encoding="utf-8"))
    if package.get("name") != "drand-client" or package.get("version") != "1.4.2":
        raise SystemExit("installed drand-client does not match the frozen verifier version")
    subprocess.run(
        [
            "node",
            str(PINNED_VERIFIER),
            "--seal",
            str(seal.resolve()),
            "--seal-publication",
            str(publication.resolve()),
            "--output",
            str(receipt.resolve()),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def main() -> int:
    args = parse_args()
    seal = json.loads(args.seal.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
    head = _git("rev-parse", "HEAD")
    if head != seal.get("subject_commit"):
        raise SystemExit("checked-out commit differs from the sealed subject commit")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked working tree must be clean for sealed FULL execution")
    freeze_digest = verify_benchmark_freeze_manifest(
        freeze_manifest, REPOSITORY_ROOT
    )
    with tempfile.TemporaryDirectory(prefix="ragwarrant-verified-beacon-") as temporary:
        receipt_path = Path(temporary) / "verified-beacon-receipt.json"
        _invoke_pinned_verifier(args.seal, args.seal_publication, receipt_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        entropy = verified_full_entropy_from_receipt(
            seal,
            receipt,
            current_timestamp=int(time.time()),
            expected_subject_commit=head,
            expected_benchmark_freeze_digest=freeze_digest,
        )
        config = load_config(args.config)
        result = run_benchmark(config, profile="FULL", verified_full_entropy=entropy)
        output_paths = list(write_benchmark_outputs(result, args.output))
        public_receipt = args.output / "verified_beacon_receipt.json"
        if public_receipt.exists():
            raise SystemExit("refusing to overwrite an existing verified beacon receipt")
        shutil.copyfile(receipt_path, public_receipt)
        output_paths.append(public_receipt)
    execution_manifest = {
        "schema_version": "1.0",
        "execution_status": "COMPLETED",
        "entropy_protocol": result["manifest"]["full_entropy_protocol"],
        "subject_commit": head,
        "benchmark_freeze_digest": freeze_digest,
        "seed_schedule_version": result["manifest"]["seed_schedule_version"],
        "seal_sha256": receipt["seal_sha256"],
        "drand": receipt["drand"],
        "verifier": receipt["verifier"],
        "full_master_seed_persisted": False,
        "scientific_results_publication_required": True,
        "output_hashes": _file_hashes(output_paths),
    }
    manifest_path = args.output / "full_execution_manifest.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(execution_manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        json.dumps(
            {
                "status": "FULL_COMPLETE_PENDING_AUTOMATIC_PUBLICATION",
                "subject_commit": head,
                "output_file_count": len(output_paths) + 1,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
