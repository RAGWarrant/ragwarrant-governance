#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "deployment_review" / "ragwarrant_brand_completion"
EXCEPTIONS_PATH = ROOT / "docs" / "migration" / "legacy_brand_exceptions.json"

LEGACY_TOKEN_PATTERNS = [
    ("legacy_token_01", re.compile(r"AIM-RAGTune")),
    ("legacy_token_02", re.compile(r"RAGTune")),
    ("legacy_token_03", re.compile(r"RAGTUNE")),
    ("legacy_token_04", re.compile(r"ragtune")),
    ("legacy_token_05", re.compile(r"rag-tuning-governance-public")),
    ("legacy_token_06", re.compile(r"rag-tuning-governance")),
    ("legacy_token_07", re.compile(r"rag_tuning_governance")),
    ("legacy_token_08", re.compile(r"aim-ragtune")),
    ("legacy_misspelling_01", re.compile(r"RAGWarrent")),
    ("legacy_misspelling_02", re.compile(r"ragwarrent")),
    ("legacy_misspelling_03", re.compile(r"RAG Warrent")),
]
MISSPELLING_IDS = {"legacy_misspelling_01", "legacy_misspelling_02", "legacy_misspelling_03"}
TEXT_SUFFIXES = {
    ".bib",
    ".cff",
    ".cfg",
    ".csv",
    ".dockerignore",
    ".gitignore",
    ".json",
    ".lock",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".tex",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_PATH_PARTS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache"}
MAX_TEXT_BYTES = 10 * 1024 * 1024
BROAD_RULE_KEYS = {"path_prefix", "path_prefixes", "path_glob", "path_globs", "glob", "globs"}
ALLOWED_CLASSIFICATIONS = {
    "migration_documentation",
    "validator_negative_fixture",
    "immutable_historical_object",
    "pre_rename_archive_manifest",
}


@dataclass(frozen=True)
class Occurrence:
    path: str
    location_type: str
    location: str
    token_id: str
    match_text: str

    def as_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "location_type": self.location_type,
            "location": self.location,
            "token_id": self.token_id,
        }


def run_git_lines(args: list[str]) -> list[str]:
    try:
        output = subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in output.splitlines() if line.strip()]


def candidate_files() -> list[Path]:
    files = set(run_git_lines(["git", "ls-files", "--cached", "--others", "--exclude-standard"]))
    if not files:
        for path in ROOT.rglob("*"):
            if path.is_file():
                files.add(path.relative_to(ROOT).as_posix())
    return sorted(Path(line) for line in files if not (set(Path(line).parts) & SKIP_PATH_PARTS))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_exception_payload() -> dict[str, object]:
    return json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))


def broad_exception_rules(rules: list[dict[str, object]]) -> list[dict[str, object]]:
    broad: list[dict[str, object]] = []
    for rule in rules:
        reasons: list[str] = []
        if BROAD_RULE_KEYS & set(rule):
            reasons.append("contains path prefix or glob keys")
        path = str(rule.get("path", ""))
        if not path:
            reasons.append("missing exact path")
        if any(char in path for char in "*?["):
            reasons.append("path contains wildcard syntax")
        if "location_type" not in rule:
            reasons.append("missing exact location_type")
        if "token_regex" not in rule:
            reasons.append("missing token_regex")
        if rule.get("classification") not in ALLOWED_CLASSIFICATIONS:
            reasons.append("classification is not in the narrow allowlist")
        if reasons:
            copy = dict(rule)
            copy["broad_rule_reasons"] = reasons
            broad.append(copy)
    return broad


def compile_rules(rules: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{**rule, "_compiled_token_regex": re.compile(str(rule["token_regex"]))} for rule in rules]


def matching_rule(hit: Occurrence, rules: list[dict[str, object]]) -> dict[str, object] | None:
    for rule in rules:
        if hit.path != rule.get("path"):
            continue
        if hit.location_type != rule.get("location_type"):
            continue
        token_regex = rule["_compiled_token_regex"]
        if token_regex.search(hit.match_text):
            return rule
    return None


def scan_text(rel_path: str, location_type: str, location_prefix: str, text: str) -> list[Occurrence]:
    hits: list[Occurrence] = []
    for token_id, pattern in LEGACY_TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            hits.append(
                Occurrence(
                    path=rel_path,
                    location_type=location_type,
                    location=f"{location_prefix}:{line_no}",
                    token_id=token_id,
                    match_text=match.group(0),
                )
            )
    return hits


def xml_visible_text(raw_xml: bytes) -> str:
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return raw_xml.decode("utf-8", errors="ignore")
    return "\n".join(node.text for node in root.iter() if node.text)


def scan_docx(rel: Path) -> list[Occurrence]:
    path = ROOT / rel
    hits: list[Occurrence] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith(".xml"):
                    hits.extend(scan_text(rel.as_posix(), "docx", name, xml_visible_text(archive.read(name))))
    except zipfile.BadZipFile:
        return hits
    return hits


def scan_pdf(rel: Path) -> list[Occurrence]:
    bundled_pdftotext = Path(sys.executable).resolve().parents[2] / "bin" / "override" / "pdftotext"
    pdftotext = shutil.which("pdftotext") or (str(bundled_pdftotext) if bundled_pdftotext.exists() else None)
    if pdftotext is None:
        return []
    proc = subprocess.run([pdftotext, str(ROOT / rel), "-"], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return []
    return scan_text(rel.as_posix(), "pdf", rel.as_posix(), proc.stdout)


def read_text_file(path: Path) -> str | None:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return None
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix not in TEXT_SUFFIXES and name not in {"dockerfile", "makefile", "license"}:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def scan_repository() -> list[Occurrence]:
    hits: list[Occurrence] = []
    for rel in candidate_files():
        rel_text = rel.as_posix()
        for token_id, pattern in LEGACY_TOKEN_PATTERNS:
            for match in pattern.finditer(rel_text):
                hits.append(
                    Occurrence(
                        path=rel_text,
                        location_type="path",
                        location="path",
                        token_id=token_id,
                        match_text=match.group(0),
                    )
                )
        absolute = ROOT / rel
        if not absolute.exists() or not absolute.is_file():
            continue
        suffix = rel.suffix.lower()
        if suffix == ".docx":
            hits.extend(scan_docx(rel))
        elif suffix == ".pdf":
            hits.extend(scan_pdf(rel))
        else:
            text = read_text_file(absolute)
            if text is not None:
                hits.extend(scan_text(rel_text, "content", rel_text, text))
    return hits


def analyze(output_root: Path) -> dict[str, object]:
    payload = load_exception_payload()
    raw_rules = list(payload.get("classifications", []))
    broad_rules = broad_exception_rules(raw_rules)
    rules = compile_rules(raw_rules) if not broad_rules else []
    hits = scan_repository()

    classified: list[dict[str, object]] = []
    unclassified: list[Occurrence] = []
    actual_counts: Counter[str] = Counter()
    by_classification: Counter[str] = Counter()
    by_token_id: Counter[str] = Counter(hit.token_id for hit in hits)
    for hit in hits:
        rule = matching_rule(hit, rules)
        if rule is None:
            unclassified.append(hit)
            continue
        rule_id = str(rule["id"])
        actual_counts[rule_id] += 1
        by_classification[str(rule["classification"])] += 1
        classified.append({"occurrence": hit.as_dict(), "rule_id": rule_id, "classification": rule["classification"]})

    max_failures = []
    sha_failures = []
    for rule in raw_rules:
        rule_id = str(rule.get("id", "missing-id"))
        maximum = int(rule.get("max_occurrences", 0))
        actual = int(actual_counts[rule_id])
        if actual > maximum:
            max_failures.append({"id": rule_id, "actual": actual, "max_occurrences": maximum})
        expected_sha = rule.get("sha256")
        path_value = rule.get("path")
        if expected_sha and path_value:
            path = ROOT / str(path_value)
            actual_sha = sha256_file(path) if path.exists() else None
            if actual_sha != expected_sha:
                sha_failures.append({"id": rule_id, "path": str(path_value), "expected": expected_sha, "actual": actual_sha})

    misspellings_outside_negative_fixtures = 0
    for item in classified:
        occurrence = item["occurrence"]
        if occurrence["token_id"] in MISSPELLING_IDS and item["classification"] != "validator_negative_fixture":
            misspellings_outside_negative_fixtures += 1
    misspellings_outside_negative_fixtures += sum(1 for hit in unclassified if hit.token_id in MISSPELLING_IDS)

    failed = bool(broad_rules or unclassified or max_failures or sha_failures or misspellings_outside_negative_fixtures)
    report = {
        "schema_version": 2,
        "result_class": "BRAND_CONSISTENCY_PASSED" if not failed else "BRAND_CONSISTENCY_FAILED",
        "canonical_product": "RAGWarrant",
        "canonical_repository": "https://github.com/RAGWarrant/ragwarrant-governance",
        "total_occurrences": len(hits),
        "classified_occurrences": len(classified),
        "unclassified_occurrences": len(unclassified),
        "active_former_name_occurrences": len(unclassified),
        "misspelling_occurrences_outside_negative_fixtures": misspellings_outside_negative_fixtures,
        "broad_exception_rules": broad_rules,
        "max_occurrence_failures": max_failures,
        "sha256_failures": sha_failures,
        "by_classification": dict(sorted(by_classification.items())),
        "by_token_id": dict(sorted(by_token_id.items())),
        "exception_actual_counts": {str(rule.get("id")): int(actual_counts[str(rule.get("id"))]) for rule in raw_rules},
        "unclassified": [hit.as_dict() for hit in unclassified[:200]],
    }

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "brand_validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# RAGWarrant Brand Validation Report",
        "",
        f"- Result: `{report['result_class']}`",
        f"- Total legacy-token occurrences: `{report['total_occurrences']}`",
        f"- Classified occurrences: `{report['classified_occurrences']}`",
        f"- Unclassified occurrences: `{report['unclassified_occurrences']}`",
        f"- Active former-name occurrences: `{report['active_former_name_occurrences']}`",
        f"- Broad exception rules: `{len(broad_rules)}`",
        "",
        "## Classification Counts",
        "",
    ]
    if by_classification:
        for key, count in sorted(by_classification.items()):
            lines.append(f"- `{key}`: `{count}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Unclassified Occurrences", ""])
    if unclassified:
        for hit in unclassified[:50]:
            lines.append(f"- `{hit.path}` `{hit.location_type}` `{hit.location}` `{hit.token_id}`")
    else:
        lines.append("- None")
    lines.append("")
    (output_root / "brand_validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RAGWarrant brand consistency with exact legacy-brand exceptions.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report = analyze(args.output_root)
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "result_class",
                    "total_occurrences",
                    "unclassified_occurrences",
                    "active_former_name_occurrences",
                    "broad_exception_rules",
                ]
            },
            sort_keys=True,
        )
    )
    if report["result_class"] != "BRAND_CONSISTENCY_PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
