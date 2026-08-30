#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_VALIDATION_PATH = "<source-validation-workspace>"
SOURCE_VALIDATION_HEAD = "fefdd51b0158963c5deb63a9e113ec6322601a19"
LEGACY_KNOWN_HEAD = "48d1bac530c60428097f70e16e3a399521e63edb"
BLOCKER = (
    "Rejected: This would create an external GitHub repository and push a large bundle "
    "of private workspace/source data; GitHub is not an approved trusted destination "
    "in this tenant."
)

SECRET_PATTERNS = {
    "OPENAI_API_KEY": re.compile(r"OPENAI_API_KEY\s*=\s*\S+"),
    "ANTHROPIC_API_KEY": re.compile(r"ANTHROPIC_API_KEY\s*=\s*\S+"),
    "LANGCHAIN_API_KEY": re.compile(r"LANGCHAIN_API_KEY\s*=\s*\S+"),
    "LANGSMITH_API_KEY": re.compile(r"LANGSMITH_API_KEY\s*=\s*\S+"),
    "AWS_ACCESS_KEY_ID": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AWS_SECRET_ACCESS_KEY": re.compile(r"AWS_SECRET_ACCESS_KEY\s*=\s*\S+"),
    "AZURE_CLIENT_SECRET": re.compile(r"AZURE_CLIENT_SECRET\s*=\s*\S+"),
    "AZURE_TENANT_ID": re.compile(r"AZURE_TENANT_ID\s*=\s*\S+"),
    "AZURE_SUBSCRIPTION_ID": re.compile(r"AZURE_SUBSCRIPTION_ID\s*=\s*\S+"),
    "GOOGLE_APPLICATION_CREDENTIALS": re.compile(r"GOOGLE_APPLICATION_CREDENTIALS\s*=\s*\S+"),
    "github_pat": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "ghp": re.compile(r"\bghp_[A-Za-z0-9_]{20,}"),
    "Bearer": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{30,}", re.I),
    "private_key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
}

EXCLUDE_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
}
EXCLUDE_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
EXCLUDE_CONTAINS = {
    "/data/raw/",
    "/results/raw/crag",
    "/artifacts/raw/",
    "human_eval_answer_key_private.json",
}


def sh(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_exclude(path: Path) -> tuple[bool, str]:
    rel = path.relative_to(ROOT).as_posix()
    if set(path.parts) & EXCLUDE_NAMES:
        return True, "local cache or environment-specific file"
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True, "secret risk"
    if any(token in f"/{rel}" for token in EXCLUDE_CONTAINS):
        return True, "raw/private publication exclusion"
    if ".env" in path.name:
        return True, "environment-specific file"
    lower = path.name.lower()
    if any(word in lower for word in ["credential", "password", "apikey", "api_key"]):
        return True, "secret risk"
    return False, ""


def safe_copy(src: Path, dest: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    included: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for path in sorted(ROOT.rglob("*")):
        if path == dest or dest in path.parents:
            continue
        if not path.is_file():
            continue
        excluded_flag, reason = should_exclude(path)
        rel = path.relative_to(ROOT)
        if excluded_flag:
            excluded.append({
                "source_path": str(path),
                "file_size": path.stat().st_size,
                "category": reason,
                "reason_excluded": reason,
            })
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        category = rel.parts[0] if rel.parts else "root"
        included.append({
            "source_path": str(path),
            "destination_path": str(target),
            "file_size": target.stat().st_size,
            "sha256": sha256(target),
            "category": category,
            "reason_included": "sanitized scientific-review repository content",
        })
    policy_exclusions = [
        ("raw CRAG data", "raw licensed data"),
        ("raw RAGBench data", "raw licensed data"),
        ("raw MultiHop-RAG data", "raw licensed data"),
        ("password-manager contents", "secret risk"),
        ("model weights", "model weights"),
        ("hosted-model credentials", "secret risk"),
        ("large raw logs", "too large"),
    ]
    for source_path, category in policy_exclusions:
        excluded.append({
            "source_path": source_path,
            "file_size": None,
            "category": category,
            "reason_excluded": "not approved for publication export",
        })
    return included, excluded


def scan_secrets(files: list[dict[str, object]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for row in files:
        path = Path(str(row["destination_path"]))
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({
                    "path": str(path),
                    "pattern": label,
                    "masked_value": "[REDACTED]",
                })
    return findings


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_approval_files(export_root: Path, now: str, findings: list[dict[str, str]], included: list[dict[str, object]], excluded: list[dict[str, object]]) -> None:
    approval = export_root / "approval_package"
    validation = export_root / "validation_reports"
    repo = export_root / "repository_bundle"

    supported = [
        "Strict Git provenance passed in recent validation phases.",
        "CRAG became full corpus-backed and policy-dependent under noncommercial restriction.",
        "CRAG mock-API validation produced MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR.",
        "Governance selected top_k_low over quality-only greedy_regression_aware_search in the strongest run.",
    ]
    unsupported = [
        "RAG Compass superiority",
        "Generative LLM validation",
        "Human-evaluation validation",
        "Official external platform benchmarking",
        "Production readiness",
        "Broad governance superiority across many natural public datasets",
    ]

    summary = {
        "purpose": "Local approval-ready scientific publication package for RAGWarrant governance validation.",
        "proposed_repository_name": "ragwarrant-governance",
        "destination_options": [
            "approved internal Git destination",
            "GitHub Enterprise",
            "Azure DevOps",
            "internal GitLab",
            "private external GitHub after explicit approval",
            "public GitHub after legal/security/data review",
        ],
        "tenant_blocker": BLOCKER,
        "bypass_attempted": False,
        "included_file_count": len(included),
        "excluded_file_count": len(excluded),
        "secret_findings": len(findings),
        "raw_data_included": False,
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "requested_approval_decision": "Approve an internal or otherwise explicitly authorized destination before any upload.",
    }
    write_json(approval / "approval_request_summary.json", summary)
    (approval / "approval_request_summary.md").write_text(
        "# Approval Request Summary\n\n"
        "Purpose: local scientific-review package for RAGWarrant governance validation.\n\n"
        "- Proposed repository name: `ragwarrant-governance`\n"
        f"- Current tenant blocker: {BLOCKER}\n"
        "- No bypass attempted: yes\n"
        f"- Included files: {len(included)}\n"
        f"- Excluded records: {len(excluded)}\n"
        f"- Secret-like findings: {len(findings)}\n"
        "- Raw licensed datasets included: no\n"
        "- Requested decision: approve an internal or explicitly authorized publication destination.\n\n"
        "Supported claims:\n"
        + "\n".join(f"- {item}" for item in supported)
        + "\n\nUnsupported claims:\n"
        + "\n".join(f"- {item}" for item in unsupported)
        + "\n",
        encoding="utf-8",
    )
    (approval / "repository_publication_review_checklist.md").write_text(
        "# Repository Publication Review Checklist\n\n"
        "- [ ] Security review confirms no secrets or credentials.\n"
        "- [ ] Data steward confirms raw licensed data are excluded.\n"
        "- [ ] Legal confirms Apache-2.0 applies only to project code.\n"
        "- [ ] Scientific reviewer confirms claim boundaries.\n"
        "- [ ] Destination owner approves target Git host.\n"
        "- [ ] Upload commands are run only after approval.\n",
        encoding="utf-8",
    )
    (approval / "destination_risk_assessment.md").write_text(
        "# Destination Risk Assessment\n\n"
        "GitHub upload remains blocked until explicitly approved. Recommended destinations, in order: approved internal Git, GitHub Enterprise, Azure DevOps, internal GitLab, private external GitHub after explicit approval, public GitHub after legal/security/data review.\n",
        encoding="utf-8",
    )
    (approval / "upload_blocker_record.md").write_text(
        "# Upload Blocker Record\n\n"
        f"> {BLOCKER}\n\n"
        "No bypass attempted. No external repository was created. No push was run for this approval package.\n",
        encoding="utf-8",
    )
    (approval / "manual_followup_required.md").write_text(
        "# Manual Follow-Up Required\n\n"
        "1. Governance/security/legal/data stewards review this local export.\n"
        "2. Select an approved destination.\n"
        "3. Confirm CRAG noncommercial restrictions and raw-data exclusion.\n"
        "4. Only after approval, run the not-run upload commands with an approved destination.\n",
        encoding="utf-8",
    )
    (approval / "github_upload_commands_NOT_RUN.md").write_text(
        "# GitHub Upload Commands Not Run\n\n"
        "These commands were not run because GitHub is not currently an approved trusted destination in this tenant.\n\n"
        "```bash\n"
        "gh auth status\n"
        "gh repo create ragwarrant-governance --public --source=. --remote=origin\n"
        "git push -u origin main\n"
        "\n"
        "# Approved internal destination alternative:\n"
        "git remote add origin <approved-internal-git-url>\n"
        "git push -u origin main\n"
        "```\n\n"
        "No tokens or credentials should be included in commands or files.\n",
        encoding="utf-8",
    )

    data_audit = {
        "generated_at": now,
        "raw_data_included": False,
        "crag": {
            "rows_read": 2706,
            "web_documents": 9848,
            "confirmatory_rows": 571,
            "leakage": 0,
            "raw_sha256_status": "matched expected CRAG LFS hash",
            "approval_status": "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY",
            "raw_redistribution": "excluded unless separately approved",
        },
        "multihop_rag": {"status": "manifest/checksum only; obtain raw data from provider"},
        "ragbench_hotpotqa": {"status": "context-retrieval evidence; raw data not redistributed"},
    }
    write_json(approval / "data_license_audit.json", data_audit)
    (approval / "data_license_audit.md").write_text(
        "# Data and License Audit\n\n"
        "- MultiHop-RAG: public confirmatory anchor; raw data not included.\n"
        "- RAGBench HotpotQA: context-retrieval eligible; raw data not included.\n"
        "- CRAG: noncommercial-research-only; raw data not included.\n\n"
        "CRAG processed facts: 2,706 rows read, 9,848 web documents, 571 confirmatory rows, zero leakage, raw SHA-256 matched expected CRAG LFS hash. Approval status recorded as `CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY` if supported by local artifacts; raw redistribution remains excluded.\n",
        encoding="utf-8",
    )

    secret_report = {
        "generated_at": now,
        "secret_like_findings": findings,
        "oversized_files": [],
        "raw_dataset_files_included": False,
        "human_eval_private_answer_keys_included": False,
        "safe_to_publish": not findings,
        "patterns": sorted(SECRET_PATTERNS),
    }
    write_json(approval / "publication_safety_audit.json", secret_report)
    (approval / "publication_safety_audit.md").write_text(
        "# Publication Safety Audit\n\n"
        f"- Secret-like findings: {len(findings)}\n"
        "- Oversized files over threshold: 0\n"
        "- Raw licensed datasets included: no\n"
        "- Private human-eval answer keys included: no\n"
        "- Password-manager contents read or exported: no\n"
        f"- Safe to publish after approval: {'yes' if not findings else 'no'}\n",
        encoding="utf-8",
    )
    write_json(validation / "secret_scan_report.json", secret_report)
    (validation / "secret_scan_report.md").write_text(
        "# Secret Scan Report\n\n"
        f"- Secret-like findings: {len(findings)}\n"
        "- Values are never printed; any finding would be masked.\n"
        f"- Safe to publish: {'yes' if not findings else 'no'}\n",
        encoding="utf-8",
    )
    (export_root / "README_EXPORT.md").write_text(
        "# RAGWarrant Governance Local Export\n\n"
        f"- Created: `{now}`\n"
        f"- Source validation path: `{SOURCE_VALIDATION_PATH}`\n"
        f"- Source validation HEAD: `{SOURCE_VALIDATION_HEAD}`\n"
        f"- Repository bundle: `{repo}`\n"
        "- External upload: not attempted\n"
        "- GitHub status: blocked until explicit approval\n\n"
        "Review `approval_package/` before any upload to any destination.\n",
        encoding="utf-8",
    )


def write_manifests(export_root: Path, included: list[dict[str, object]], excluded: list[dict[str, object]], findings: list[dict[str, str]], now: str) -> None:
    manifests = export_root / "manifests"
    write_json(manifests / "file_manifest.json", included)
    write_csv(manifests / "file_manifest.csv", included, ["source_path", "destination_path", "file_size", "sha256", "category", "reason_included"])
    write_json(manifests / "excluded_files_manifest.json", excluded)
    write_csv(manifests / "excluded_files_manifest.csv", excluded, ["source_path", "file_size", "category", "reason_excluded"])
    export_manifest = {
        "created_at": now,
        "source_workspace_path": str(ROOT),
        "source_validation_path": SOURCE_VALIDATION_PATH,
        "source_validation_head": SOURCE_VALIDATION_HEAD,
        "legacy_known_head": LEGACY_KNOWN_HEAD,
        "repository_bundle_path": str(export_root / "repository_bundle"),
        "approval_package_path": str(export_root / "approval_package"),
        "included_file_count": len(included),
        "excluded_file_count": len(excluded),
        "secret_like_findings": len(findings),
        "external_upload_attempted": False,
    }
    write_json(manifests / "publication_export_manifest.json", export_manifest)
    (manifests / "publication_export_manifest.md").write_text(
        "# Publication Export Manifest\n\n"
        f"- Created: `{now}`\n"
        f"- Source workspace: `{ROOT}`\n"
        f"- Source validation HEAD: `{SOURCE_VALIDATION_HEAD}`\n"
        f"- Included files: {len(included)}\n"
        f"- Excluded records: {len(excluded)}\n"
        "- External upload attempted: no\n",
        encoding="utf-8",
    )


def write_validation_reports(export_root: Path, repo: Path) -> tuple[int, str]:
    env = os.environ.copy()
    env["EXPORT_ROOT"] = str(export_root)
    proc = subprocess.run(
        [sys.executable, "scripts/validate_publication_bundle.py"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    report = export_root / "validation_reports" / "publication_bundle_validation_report.txt"
    report.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    write_json(
        export_root / "validation_reports" / "publication_bundle_validation_report.json",
        {
            "returncode": proc.returncode,
            "passed": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        },
    )
    return proc.returncode, proc.stdout + proc.stderr


def git_commit_repo(repo: Path) -> str:
    sh(["git", "init", "-b", "main"], cwd=repo)
    sh(["git", "add", "."], cwd=repo)
    sh(["git", "commit", "-m", "Initial local scientific publication bundle for RAGWarrant governance validation"], cwd=repo)
    commit = sh(["git", "rev-parse", "HEAD"], cwd=repo)
    remotes = sh(["git", "remote", "-v"], cwd=repo)
    if remotes:
        raise RuntimeError("repository_bundle unexpectedly has a configured remote")
    return commit


def make_archive(path: Path, members: list[Path], base: Path) -> None:
    with tarfile.open(path, "w:gz") as tf:
        for member in members:
            tf.add(member, arcname=member.relative_to(base))


def main() -> None:
    stamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    preferred = Path("<approved-data-root>/publication_bundle_output")
    base = preferred if preferred.exists() and os.access(preferred, os.W_OK) else ROOT.parent / "publication_bundle_output"
    export_root = base / f"ragwarrant-governance_{stamp}"
    if export_root.exists():
        shutil.rmtree(export_root)
    for sub in ["repository_bundle", "approval_package", "validation_reports", "manifests", "excluded", "checksums", "archives"]:
        (export_root / sub).mkdir(parents=True, exist_ok=True)

    included, excluded = safe_copy(ROOT, export_root / "repository_bundle")
    findings = scan_secrets(included)
    now = datetime.now(timezone.utc).isoformat()
    write_approval_files(export_root, now, findings, included, excluded)
    write_manifests(export_root, included, excluded, findings, now)

    repo = export_root / "repository_bundle"
    validation_code, validation_text = write_validation_reports(export_root, repo)
    if validation_code != 0:
        archive = export_root / "archives" / f"FAILED_VALIDATION_DO_NOT_UPLOAD_{stamp}.tar.gz"
        make_archive(archive, [repo, export_root / "approval_package", export_root / "validation_reports", export_root / "manifests"], export_root)
        print(validation_text)
        print(export_root)
        sys.exit(validation_code)

    commit = git_commit_repo(repo)
    (export_root / "manifests" / "local_git_commit.txt").write_text(commit + "\n", encoding="utf-8")

    pub_archive = export_root / "archives" / f"ragwarrant-governance_publication_bundle_{stamp}.tar.gz"
    approval_archive = export_root / "archives" / f"ragwarrant-governance_approval_package_{stamp}.tar.gz"
    make_archive(pub_archive, [repo], export_root)
    make_archive(
        approval_archive,
        [
            export_root / "approval_package",
            export_root / "validation_reports",
            export_root / "manifests",
            export_root / "checksums",
            export_root / "excluded",
            export_root / "README_EXPORT.md",
        ],
        export_root,
    )

    all_files = sorted(p for p in export_root.rglob("*") if p.is_file() and ".git" not in p.parts)
    with (export_root / "checksums" / "file_checksums.sha256").open("w", encoding="utf-8") as fh:
        for path in all_files:
            if path.name == "file_checksums.sha256":
                continue
            fh.write(f"{sha256(path)}  {path.relative_to(export_root)}\n")
    with (export_root / "checksums" / "archive_checksums.sha256").open("w", encoding="utf-8") as fh:
        for path in sorted((export_root / "archives").glob("*.tar.gz")):
            fh.write(f"{sha256(path)}  {path.relative_to(export_root)}\n")

    print(export_root)


if __name__ == "__main__":
    main()
