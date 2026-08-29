from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import write_json


DECISIONS = {"PROMOTE", "BLOCK", "REJECT", "INCONCLUSIVE", "ERROR"}


def decision_from_result_class(result_class: str) -> str:
    if "PROMOTE" in result_class or "PASSED" in result_class or "SUPPORTED" in result_class:
        return "PROMOTE"
    if "BLOCK" in result_class or "FAIL_CLOSED" in result_class:
        return "BLOCK"
    if "NEGATIVE" in result_class or "QUALITY_LOSS" in result_class:
        return "REJECT"
    if "INCONCLUSIVE" in result_class or "MIXED" in result_class:
        return "INCONCLUSIVE"
    return "INCONCLUSIVE"


def build_promotion_decision(
    *,
    run_id: str,
    suite: str,
    result_class: str,
    selected_policy: str = "",
    baseline_policy: str = "",
    decision_reason: str = "",
    artifact_uris: list[str] | None = None,
    validator_status: str = "not_run",
    deltas: dict[str, float] | None = None,
    risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    values = deltas or {}
    decision = decision_from_result_class(result_class)
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "suite": suite,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "result_class": result_class,
        "decision": decision,
        "decision_reason": decision_reason or result_class,
        "selected_policy": selected_policy,
        "baseline_policy": baseline_policy,
        "quality_delta": values.get("quality_delta", 0.0),
        "cost_delta": values.get("cost_delta", 0.0),
        "latency_delta": values.get("latency_delta", 0.0),
        "evidence_support_delta": values.get("evidence_support_delta", 0.0),
        "risk_flags": risk_flags or [],
        "claim_boundaries": {
            "rag_compass_superiority": "unsupported",
            "human_validation": "unsupported",
            "official_platform_benchmarking": "unsupported",
            "production_readiness": "unsupported",
            "rag_compass_superiority_claimed": False,
            "human_validation_claimed": False,
            "official_platform_benchmarking_claimed": False,
            "production_readiness_claimed": False,
            "hallucination_elimination_claimed": False,
        },
        "artifact_uris": artifact_uris or [],
        "validator_status": validator_status,
    }


def write_promotion_decision(path: Path, payload: dict[str, Any]) -> None:
    if payload.get("decision") not in DECISIONS:
        payload["decision"] = "ERROR"
    write_json(path, payload)
