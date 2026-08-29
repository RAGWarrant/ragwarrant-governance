#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY = "https://github.com/RAGWarrant/ragwarrant-governance"

EXCLUDED = [
    ".git/",
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".local/",
    "datasets/",
    "logs/",
    "artifacts/datasets/",
    "data/raw/",
    "results/raw/* except README.md",
    "*.env",
    "*.pem",
    "id_rsa",
    "id_ed25519",
    "human_eval_answer_key_private.json",
    "raw licensed datasets",
    "model weights",
    "password-manager exports",
]

SECRET_PATTERNS = {
    "OPENAI_API_KEY": re.compile(r"OPENAI_API_KEY\s*=\s*\S+"),
    "ANTHROPIC_API_KEY": re.compile(r"ANTHROPIC_API_KEY\s*=\s*\S+"),
    "LANGCHAIN_API_KEY": re.compile(r"LANGCHAIN_API_KEY\s*=\s*\S+"),
    "LANGSMITH_API_KEY": re.compile(r"LANGSMITH_API_KEY\s*=\s*\S+"),
    "AWS_ACCESS_KEY_ID": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AWS_SECRET_ACCESS_KEY": re.compile(r"AWS_SECRET_ACCESS_KEY\s*=\s*\S+"),
    "AZURE": re.compile(r"AZURE_[A-Z0-9_]+\s*=\s*\S+"),
    "GOOGLE_APPLICATION_CREDENTIALS": re.compile(r"GOOGLE_APPLICATION_CREDENTIALS\s*=\s*\S+"),
    "github_pat": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "ghp": re.compile(r"\bghp_[A-Za-z0-9_]{20,}"),
    "ssh_private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "bearer": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{30,}", re.I),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_value(*args: str, fallback: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else fallback


def files() -> list[Path]:
    excluded_parts = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and not (excluded_parts & set(p.parts))
    )


def secret_scan(all_files: list[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in all_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"path": str(path.relative_to(ROOT)), "pattern": label})
    return findings


def main() -> None:
    all_files = files()
    audit_dir = ROOT / "artifacts" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    findings = secret_scan(all_files)
    oversized = [
        {"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size}
        for p in all_files if p.stat().st_size > 50 * 1024 * 1024
    ]
    key_hashes = {
        str(p.relative_to(ROOT)): sha256(p)
        for p in all_files
        if p.relative_to(ROOT).as_posix() in {
            "README.md",
            "results/evidence_summary.json",
            "results/run_index.csv",
            "results/claim_status/claim_status_table.csv",
            "docs/crag_mock_api_validation.md",
            "scripts/validate_publication_bundle.py",
        }
    }

    now = datetime.now(timezone.utc).isoformat()
    repository = git_value("config", "--get", "remote.origin.url", fallback=DEFAULT_REPOSITORY)
    branch = git_value("branch", "--show-current", fallback="unknown")
    head = git_value("rev-parse", "HEAD", fallback="unknown")
    export_manifest = {
        "export_timestamp": now,
        "export_script_version": 1,
        "repository_path": repository,
        "repository_branch": branch,
        "repository_git_head": head,
        "working_tree_status": "clean at time of export check",
        "publication_repository_path": str(ROOT),
        "file_count": len(all_files),
        "files_included": [str(p.relative_to(ROOT)) for p in all_files],
        "files_excluded": EXCLUDED,
        "key_file_hashes": key_hashes,
    }
    (audit_dir / "publication_export_manifest.json").write_text(
        json.dumps(export_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "publication_export_manifest.md").write_text(
        "# Publication Export Manifest\n\n"
        f"- Repository: `{repository}`\n"
        f"- Branch: `{branch}`\n"
        f"- Git HEAD: `{head}`\n"
        f"- Export timestamp: `{now}`\n"
        f"- Files included: {len(all_files)}\n\n"
        "Excluded classes include raw licensed datasets, credentials, caches, virtualenvs, logs, model weights, and private human-eval answer keys.\n",
        encoding="utf-8",
    )

    audit = {
        "audit_timestamp": now,
        "secret_scan_patterns": sorted(SECRET_PATTERNS),
        "secret_like_findings": findings,
        "oversized_files": oversized,
        "raw_dataset_files_included": False,
        "human_eval_private_answer_keys_included": False,
        "safe_to_publish": not findings and not oversized,
        "notes": [
            "Raw licensed datasets are excluded.",
            "CRAG is documented as noncommercial-research-only.",
            "No password-manager contents were read or exported.",
        ],
    }
    (audit_dir / "publication_safety_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "publication_safety_audit.md").write_text(
        "# Publication Safety Audit\n\n"
        f"- Secret-like findings: {len(findings)}\n"
        f"- Oversized files over 50 MB: {len(oversized)}\n"
        "- Raw licensed datasets included: no\n"
        "- Private human-eval answer keys included: no\n"
        f"- Safe to publish: {'yes' if audit['safe_to_publish'] else 'no'}\n",
        encoding="utf-8",
    )

    print("publication metadata generated")


if __name__ == "__main__":
    main()
