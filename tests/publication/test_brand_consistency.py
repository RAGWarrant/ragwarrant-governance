from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_brand_consistency_validator_passes(tmp_path: Path) -> None:
    report_root = tmp_path / "brand-report"
    subprocess.run(
        [
            sys.executable,
            "scripts/validate_brand_consistency.py",
            "--output-root",
            str(report_root),
        ],
        cwd=ROOT,
        check=True,
    )

    report = json.loads((report_root / "brand_validation_report.json").read_text(encoding="utf-8"))
    assert report["result_class"] == "BRAND_CONSISTENCY_PASSED"
    assert report["unclassified_occurrences"] == 0
    assert report["active_former_name_occurrences"] == 0
    assert report["broad_exception_rules"] == []
    assert report["misspelling_occurrences_outside_negative_fixtures"] == 0
    assert report["max_occurrence_failures"] == []
