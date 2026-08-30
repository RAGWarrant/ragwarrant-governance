#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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

LEGACY_PATTERNS = {
    "AIM-RAGTune": re.compile(r"AIM-RAGTune"),
    "RAGTune": re.compile(r"RAGTune"),
    "RAGTUNE": re.compile(r"RAGTUNE"),
    "ragtune": re.compile(r"ragtune"),
    "rag-tuning-governance-public": re.compile(r"rag-tuning-governance-public"),
    "rag-tuning-governance": re.compile(r"rag-tuning-governance"),
    "rag_tuning_governance": re.compile(r"rag_tuning_governance"),
    "aim-ragtune": re.compile(r"aim-ragtune"),
    "RAGWarrent": re.compile(r"RAGWarrent"),
    "ragwarrent": re.compile(r"ragwarrent"),
    "RAG Warrent": re.compile(r"RAG Warrent"),
}

MISSPELLINGS = {"RAGWarrent", "ragwarrent", "RAG Warrent"}
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


@dataclass(frozen=True)
class Occurrence:
    path: str
    location: str
    token: str
    match: str
    context: str
    classification: str | None
    rationale: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "path": self.path,
            "location": self.location,
            "token": self.token,
            "match": self.match,
            "context": self.context,
            "classification": self.classification,
            "rationale": self.rationale,
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
                rel = path.relative_to(ROOT).as_posix()
                if not (set(Path(rel).parts) & SKIP_PATH_PARTS):
                    files.add(rel)
    return sorted(Path(line) for line in files if not (set(Path(line).parts) & SKIP_PATH_PARTS))


def load_exception_rules() -> list[dict[str, object]]:
    payload = json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    return list(payload.get("classifications", []))


def looks_like_historical_identifier(token: str, context: str) -> bool:
    if token != "ragtune":
        return False
    historical_markers = [
        "run_id",
        "run id",
        "suite",
        "artifacts/ragtune",
        "configs/experiments/ragtune_",
    ]
    if any(marker in context for marker in historical_markers):
        return True
    return bool(re.search(r"ragtune_[a-z0-9_]+_v[0-9]", context))


def classify(path: str, token: str, rules: list[dict[str, object]], context: str = "") -> tuple[str | None, str | None]:
    if token in MISSPELLINGS:
        if path == "scripts/validate_brand_consistency.py":
            return "migration_documentation", "The validator enumerates misspellings so it can reject them elsewhere."
        return None, None
    if looks_like_historical_identifier(token, context):
        return "historical_run_identifier", "Immutable pre-rename run, suite, config, or artifact identifier."
    for rule in rules:
        exact = set(str(item) for item in rule.get("path_exact", []))
        prefixes = tuple(str(item) for item in rule.get("path_prefixes", []))
        if path in exact or (prefixes and path.startswith(prefixes)):
            return str(rule["classification"]), str(rule.get("rationale", ""))
    return None, None


def short_context(text: str, start: int, end: int, width: int = 96) -> str:
    begin = max(0, start - width // 2)
    finish = min(len(text), end + width // 2)
    return " ".join(text[begin:finish].replace("\n", " ").split())


def scan_text(path: str, location_prefix: str, text: str, rules: list[dict[str, object]]) -> list[Occurrence]:
    hits: list[Occurrence] = []
    for token, pattern in LEGACY_PATTERNS.items():
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            context = short_context(text, match.start(), match.end())
            classification, rationale = classify(path, token, rules, context)
            hits.append(
                Occurrence(
                    path=path,
                    location=f"{location_prefix}:{line_no}",
                    token=token,
                    match=match.group(0),
                    context=context,
                    classification=classification,
                    rationale=rationale,
                )
            )
    return hits


def xml_visible_text(raw_xml: bytes) -> str:
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return raw_xml.decode("utf-8", errors="ignore")
    pieces = [node.text for node in root.iter() if node.text]
    return "\n".join(pieces)


def scan_docx(rel: Path, rules: list[dict[str, object]]) -> list[Occurrence]:
    path = ROOT / rel
    hits: list[Occurrence] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                text = xml_visible_text(archive.read(name))
                hits.extend(scan_text(rel.as_posix(), name, text, rules))
    except zipfile.BadZipFile:
        return hits
    return hits


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
    rules = load_exception_rules()
    hits: list[Occurrence] = []
    for rel in candidate_files():
        rel_text = rel.as_posix()
        if rel_text in {
            "deployment_review/ragwarrant_brand_completion/brand_validation_report.json",
            "deployment_review/ragwarrant_brand_completion/brand_validation_report.md",
        }:
            continue
        classification, rationale = classify(rel_text, "ragtune", rules)
        for token, pattern in LEGACY_PATTERNS.items():
            if pattern.search(rel_text):
                path_classification, path_rationale = classify(rel_text, token, rules, rel_text)
                hits.append(
                    Occurrence(
                        path=rel_text,
                        location="path",
                        token=token,
                        match=pattern.search(rel_text).group(0),
                        context=rel_text,
                        classification=path_classification,
                        rationale=path_rationale,
                    )
                )
        absolute = ROOT / rel
        if not absolute.exists() or not absolute.is_file():
            continue
        if rel.suffix.lower() == ".docx":
            hits.extend(scan_docx(rel, rules))
            continue
        text = read_text_file(absolute)
        if text is not None:
            hits.extend(scan_text(rel_text, rel_text, text, rules))
        _ = classification, rationale
    return hits


def write_reports(hits: list[Occurrence], output_root: Path) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    classified = [hit for hit in hits if hit.classification]
    unclassified = [hit for hit in hits if not hit.classification]
    by_classification = Counter(hit.classification for hit in classified)
    by_token = Counter(hit.token for hit in hits)
    report = {
        "result_class": "BRAND_CONSISTENCY_PASSED" if not unclassified else "BRAND_CONSISTENCY_FAILED",
        "canonical_product": "RAGWarrant",
        "canonical_repository": "https://github.com/RAGWarrant/ragwarrant-governance",
        "total_occurrences": len(hits),
        "classified_occurrences": len(classified),
        "unclassified_occurrences": len(unclassified),
        "by_classification": dict(sorted(by_classification.items())),
        "by_token": dict(sorted(by_token.items())),
        "unclassified": [hit.as_dict() for hit in unclassified[:200]],
        "classified_samples": [hit.as_dict() for hit in classified[:200]],
    }
    (output_root / "brand_validation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# RAGWarrant Brand Validation Report",
        "",
        f"- Result: `{report['result_class']}`",
        f"- Canonical repository: `{report['canonical_repository']}`",
        f"- Total former-name occurrences: {report['total_occurrences']}",
        f"- Classified occurrences: {report['classified_occurrences']}",
        f"- Unclassified occurrences: {report['unclassified_occurrences']}",
        "",
        "## Classifications",
        "",
    ]
    if by_classification:
        for key, count in sorted(by_classification.items()):
            lines.append(f"- `{key}`: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "## Unclassified Occurrences", ""])
    if unclassified:
        for hit in unclassified[:50]:
            lines.append(f"- `{hit.path}` {hit.location}: `{hit.match}`")
    else:
        lines.append("- None")
    lines.append("")
    (output_root / "brand_validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RAGWarrant brand consistency.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report = write_reports(scan_repository(), args.output_root)
    print(json.dumps({k: report[k] for k in ["result_class", "total_occurrences", "unclassified_occurrences"]}))
    if report["unclassified_occurrences"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
