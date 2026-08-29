from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ragwarrant.utils.files import write_json, write_text


def write_report(
    run_dir: Path,
    *,
    suite: str,
    run_id: str,
    dataset_manifest: dict[str, Any],
    ranking: pd.DataFrame,
    certificate: dict[str, Any],
    skipped_baselines: list[dict[str, Any]],
    statistical_analysis: dict[str, Any],
    utility_sensitivity: dict[str, Any],
) -> None:
    write_json(run_dir / "certificate.json", certificate)
    write_json(run_dir / "statistical_analysis.json", statistical_analysis)
    write_json(run_dir / "utility_sensitivity.json", utility_sensitivity)
    winner = certificate.get("winner")
    lines = [
        f"# {suite}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Dataset: {dataset_manifest.get('name')}",
        f"- Rows: {dataset_manifest.get('row_count')}",
        f"- Fixture: {dataset_manifest.get('fixture')}",
        f"- Winner: `{winner}`",
        f"- Certificate: {certificate.get('status')}",
        "",
        "## Baseline Ranking",
        "",
    ]
    for rank, row in enumerate(ranking.to_dict(orient="records"), start=1):
        lines.append(
            f"{rank}. `{row['policy_id']}`: cost-adjusted={row.get('cost_adjusted_utility', 0):.4f}, "
            f"quality={row.get('raw_quality', 0):.4f}, cost={row.get('cost', 0):.4f}, "
            f"latency_p95={row.get('latency_p95', 0):.4f}"
        )
    lines.extend(
        [
            "",
            "## Baselines Skipped",
            "",
        ]
    )
    if skipped_baselines:
        lines.extend(f"- `{row['baseline_name']}`: {row['reason']}" for row in skipped_baselines)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "This result supports only the observed software-validation outcome under declared assumptions.",
            "This result suggests candidate directions only when certificates say so.",
            "This result is inconclusive when fixture data, weak effects, or unstable utility dominate.",
            "This claim is refused when protected regression, null controls, or simpler baselines dominate.",
            "",
            "This is a fixture/smoke test and should not be cited as benchmark evidence."
            if dataset_manifest.get("fixture")
            else "This run used non-fixture data according to its manifest.",
        ]
    )
    write_text(run_dir / "report.md", "\n".join(lines) + "\n")

