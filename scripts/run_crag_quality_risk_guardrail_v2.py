#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean


TWO_ITEM_POLICY = "pareto_frontier_selector"
EXPANDED_POLICY = "expanded_retrieval_multi_endpoint"
LOW_POLICY = "low_retrieval_single_endpoint"
V2_POLICY = "quality_risk_guardrail_v2_pooled_cross_offset"
MARGIN = 0.01
POSITIVE_LATENCY_CLASS = "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY_CRAG"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def ci(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    ordered = sorted(values)
    return {
        "mean": mean(values),
        "ci_low": ordered[int(0.025 * (len(ordered) - 1))],
        "ci_high": ordered[int(0.975 * (len(ordered) - 1))],
    }


def f(row: dict[str, str], key: str) -> float:
    return float(row.get(key, "0") or 0.0)


def example_groups(input_roots: list[Path]) -> list[dict[str, object]]:
    examples: list[dict[str, object]] = []
    for root in input_roots:
        stats = json.loads((root / "primary_outcome_statistics.json").read_text(encoding="utf-8"))
        rows = read_rows(root / "per_query_generation_metrics.csv")
        by_example: dict[str, dict[str, dict[str, str]]] = {}
        for row in rows:
            by_example.setdefault(row["example_id"], {})[row["policy_id"]] = row
        for example_id, policies in by_example.items():
            if TWO_ITEM_POLICY not in policies or EXPANDED_POLICY not in policies or LOW_POLICY not in policies:
                continue
            low = policies[LOW_POLICY]
            two = policies[TWO_ITEM_POLICY]
            expanded = policies[EXPANDED_POLICY]
            low_context_count = f(two, "api_call_count")
            expanded_context_count = f(expanded, "api_call_count")
            low_context_token_estimate = max(0.0, (f(two, "retrieval_cost_units") - low_context_count) * 1000.0)
            expanded_context_token_estimate = max(
                0.0,
                (f(expanded, "retrieval_cost_units") - expanded_context_count) * 1000.0,
            )
            examples.append(
                {
                    "offset": int(stats.get("sample_offset", 0) or 0),
                    "example_id": example_id,
                    "split": two["split"],
                    "two_policy": two,
                    "expanded_policy": expanded,
                    "features": {
                        "low_context_count": low_context_count,
                        "expanded_context_count": expanded_context_count,
                        "low_context_token_estimate": low_context_token_estimate,
                        "expanded_context_token_estimate": expanded_context_token_estimate,
                        "context_token_gap": expanded_context_token_estimate - low_context_token_estimate,
                        "retrieval_cost_gap": f(expanded, "retrieval_cost_units") - f(two, "retrieval_cost_units"),
                        "low_input_token_estimate": f(two, "input_token_estimate"),
                        "expanded_input_token_estimate": f(expanded, "input_token_estimate"),
                        "input_token_gap": f(expanded, "input_token_estimate") - f(two, "input_token_estimate"),
                    },
                    "two_quality": f(two, "final_generated_quality_score"),
                    "expanded_quality": f(expanded, "final_generated_quality_score"),
                    "two_latency": f(two, "total_latency_ms"),
                    "expanded_latency": f(expanded, "total_latency_ms"),
                    "two_cost": f(two, "total_cost_units"),
                    "expanded_cost": f(expanded, "total_cost_units"),
                    "two_api_calls": f(two, "api_call_count"),
                    "expanded_api_calls": f(expanded, "api_call_count"),
                }
            )
    return examples


def candidate_rules(training_examples: list[dict[str, object]]) -> list[dict[str, object]]:
    features = [
        "low_context_token_estimate",
        "expanded_context_token_estimate",
        "context_token_gap",
        "retrieval_cost_gap",
        "low_input_token_estimate",
        "expanded_input_token_estimate",
        "input_token_gap",
    ]
    rules: list[dict[str, object]] = [
        {"rule_id": "never_expand", "feature_name": "low_context_count", "operator": ">=", "threshold": 10**9},
        {"rule_id": "always_expand", "feature_name": "low_context_count", "operator": ">=", "threshold": 0},
    ]
    for feature in features:
        values = sorted({float(example["features"][feature]) for example in training_examples})  # type: ignore[index]
        for threshold in values:
            rules.append(
                {
                    "rule_id": f"expand_when_{feature}_le_{threshold:g}",
                    "feature_name": feature,
                    "operator": "<=",
                    "threshold": threshold,
                }
            )
            rules.append(
                {
                    "rule_id": f"expand_when_{feature}_ge_{threshold:g}",
                    "feature_name": feature,
                    "operator": ">=",
                    "threshold": threshold,
                }
            )
    return rules


def predicts_expand(rule: dict[str, object], example: dict[str, object]) -> bool:
    value = float(example["features"][str(rule["feature_name"])])  # type: ignore[index]
    threshold = float(rule["threshold"])
    if rule["operator"] == "<=":
        return value <= threshold
    return value >= threshold


def evaluate_rule(rule: dict[str, object], examples: list[dict[str, object]]) -> dict[str, object]:
    quality_deltas: list[float] = []
    cost_deltas: list[float] = []
    latency_deltas: list[float] = []
    api_deltas: list[float] = []
    expanded_count = 0
    unprotected_quality_risk_count = 0
    for example in examples:
        expand = predicts_expand(rule, example)
        expanded_count += int(expand)
        governed_quality = float(example["expanded_quality"] if expand else example["two_quality"])
        governed_cost = float(example["expanded_cost"] if expand else example["two_cost"])
        governed_latency = float(example["expanded_latency"] if expand else example["two_latency"])
        governed_api = float(example["expanded_api_calls"] if expand else example["two_api_calls"])
        baseline_quality = float(example["expanded_quality"])
        quality_deltas.append(governed_quality - baseline_quality)
        cost_deltas.append(governed_cost - float(example["expanded_cost"]))
        latency_deltas.append(governed_latency - float(example["expanded_latency"]))
        api_deltas.append(governed_api - float(example["expanded_api_calls"]))
        if not expand and governed_quality < baseline_quality - MARGIN:
            unprotected_quality_risk_count += 1
    expansion_rate = expanded_count / max(1, len(examples))
    quality = ci(quality_deltas)
    latency = ci(latency_deltas)
    result_class = "GEN_LLM_GOVERNANCE_INCONCLUSIVE_CRAG"
    if quality["mean"] < -MARGIN and (ci(cost_deltas)["mean"] < 0 or latency["mean"] < 0):
        result_class = "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS_CRAG"
    elif quality["mean"] >= -MARGIN and latency["ci_high"] < 0:
        result_class = POSITIVE_LATENCY_CLASS
    return {
        "example_count": len(examples),
        "expansion_rate": expansion_rate,
        "expanded_count": expanded_count,
        "unprotected_quality_risk_count": unprotected_quality_risk_count,
        "generated_quality_delta": quality,
        "cost_delta": ci(cost_deltas),
        "latency_delta_ms": latency,
        "api_call_delta": ci(api_deltas),
        "result_class": result_class,
    }


def train_rule(training_examples: list[dict[str, object]]) -> tuple[dict[str, object] | None, dict[str, object], list[dict[str, object]]]:
    validation = [example for example in training_examples if example["split"] == "validation"]
    if not validation:
        validation = [example for example in training_examples if example["split"] == "calibration"] or training_examples
    rows: list[dict[str, object]] = []
    feasible: list[tuple[dict[str, object], dict[str, object]]] = []
    for rule in candidate_rules(validation):
        metrics = evaluate_rule(rule, validation)
        row = {
            **rule,
            **metrics,
            "validation_generated_quality_delta_mean": metrics["generated_quality_delta"]["mean"],  # type: ignore[index]
            "validation_latency_delta_ci_high": metrics["latency_delta_ms"]["ci_high"],  # type: ignore[index]
            "validation_unprotected_quality_risk_count": metrics["unprotected_quality_risk_count"],
            "deployable_features_only": True,
            "raw_text_features_used": False,
        }
        rows.append(row)
        if (
            float(metrics["expansion_rate"]) < 1.0
            and float(metrics["generated_quality_delta"]["mean"]) >= -MARGIN  # type: ignore[index]
            and int(metrics["unprotected_quality_risk_count"]) == 0
        ):
            feasible.append((rule, metrics))
    if not feasible:
        return None, {
            "predictor_result_class": "CRAG_GEN_LLM_RISK_GUARDRAIL_V2_VALIDATION_GATE_FAILED",
            "training_row_count": len(validation),
            "quality_noninferiority_margin": MARGIN,
            "deployable_features_only": True,
            "raw_text_features_used": False,
        }, rows
    selected, selected_metrics = min(
        feasible,
        key=lambda item: (
            float(item[1]["expansion_rate"]),
            float(item[1]["latency_delta_ms"]["mean"]),  # type: ignore[index]
            -float(item[1]["generated_quality_delta"]["mean"]),  # type: ignore[index]
            str(item[0]["rule_id"]),
        ),
    )
    return selected, {
        **selected,
        **selected_metrics,
        "predictor_result_class": "CRAG_GEN_LLM_RISK_GUARDRAIL_V2_VALIDATION_GATE_PASSED",
        "training_row_count": len(validation),
        "quality_noninferiority_margin": MARGIN,
        "gate_requires_less_than_always_expand": True,
        "gate_requires_validation_noninferiority": True,
        "gate_requires_no_unprotected_validation_quality_risk": True,
        "deployable_features_only": True,
        "raw_text_features_used": False,
    }, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-roots", nargs="+", required=True)
    parser.add_argument("--output-root", default="artifacts/generative_llm_validation/crag_quality_risk_guardrail_v2")
    parser.add_argument("--results-root", default="results/generative_llm_validation")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    results_root = Path(args.results_root)
    output_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)
    examples = example_groups([Path(item) for item in args.input_roots])
    offsets = sorted({int(example["offset"]) for example in examples})
    heldout_rows: list[dict[str, object]] = []
    predictor_rows: list[dict[str, object]] = []
    training_rows: list[dict[str, object]] = []
    for heldout in offsets:
        training = [example for example in examples if int(example["offset"]) != heldout]
        test = [example for example in examples if int(example["offset"]) == heldout and example["split"] == "confirmatory_test"]
        if not test:
            test = [example for example in examples if int(example["offset"]) == heldout]
        rule, metrics, candidates = train_rule(training)
        for candidate in candidates:
            predictor_rows.append({"heldout_offset": heldout, **candidate})
        for example in training:
            if example["split"] in {"validation", "calibration"}:
                training_rows.append(
                    {
                        "heldout_offset": heldout,
                        "training_offset": example["offset"],
                        "example_id": example["example_id"],
                        "split": example["split"],
                        "two_item_quality": example["two_quality"],
                        "expanded_quality": example["expanded_quality"],
                        "label_quality_risk": float(example["two_quality"]) < float(example["expanded_quality"]) - MARGIN,
                    }
                )
        if rule is None:
            heldout_rows.append(
                {
                    "heldout_offset": heldout,
                    "result_class": "GEN_LLM_VALIDATION_BLOCKED_PREDICTOR_GATE_CRAG",
                    "predictor_result_class": metrics["predictor_result_class"],
                    "example_count": len(test),
                    "expansion_rate": "",
                    "generated_quality_delta_mean": "",
                    "generated_quality_delta_ci_low": "",
                    "generated_quality_delta_ci_high": "",
                    "latency_delta_ms_mean": "",
                    "latency_delta_ms_ci_low": "",
                    "latency_delta_ms_ci_high": "",
                    "cost_delta_mean": "",
                    "api_call_delta_mean": "",
                    "quality_loss_blocked": True,
                }
            )
            continue
        test_metrics = evaluate_rule(rule, test)
        quality_delta = test_metrics["generated_quality_delta"]
        quality_loss_blocked = (
            int(test_metrics["unprotected_quality_risk_count"]) > 0
            or float(quality_delta["mean"]) < -MARGIN  # type: ignore[index]
        )
        heldout_rows.append(
            {
                "heldout_offset": heldout,
                "result_class": (
                    "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS_CRAG"
                    if quality_loss_blocked
                    else test_metrics["result_class"]
                ),
                "predictor_result_class": metrics["predictor_result_class"],
                "rule_id": rule["rule_id"],
                "feature_name": rule["feature_name"],
                "operator": rule["operator"],
                "threshold": rule["threshold"],
                "example_count": len(test),
                "expansion_rate": test_metrics["expansion_rate"],
                "unprotected_quality_risk_count": test_metrics["unprotected_quality_risk_count"],
                "generated_quality_delta_mean": quality_delta["mean"],  # type: ignore[index]
                "generated_quality_delta_ci_low": quality_delta["ci_low"],  # type: ignore[index]
                "generated_quality_delta_ci_high": quality_delta["ci_high"],  # type: ignore[index]
                "latency_delta_ms_mean": test_metrics["latency_delta_ms"]["mean"],  # type: ignore[index]
                "latency_delta_ms_ci_low": test_metrics["latency_delta_ms"]["ci_low"],  # type: ignore[index]
                "latency_delta_ms_ci_high": test_metrics["latency_delta_ms"]["ci_high"],  # type: ignore[index]
                "cost_delta_mean": test_metrics["cost_delta"]["mean"],  # type: ignore[index]
                "api_call_delta_mean": test_metrics["api_call_delta"]["mean"],  # type: ignore[index]
                "quality_loss_blocked": quality_loss_blocked,
            }
        )
    quality_loss_count = sum(1 for row in heldout_rows if row.get("quality_loss_blocked") is True)
    positive_latency_count = sum(1 for row in heldout_rows if row.get("result_class") == POSITIVE_LATENCY_CLASS)
    gate_passed_count = sum(1 for row in heldout_rows if row.get("predictor_result_class") == "CRAG_GEN_LLM_RISK_GUARDRAIL_V2_VALIDATION_GATE_PASSED")
    if gate_passed_count < len(heldout_rows):
        result_class = "CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_VALIDATION_GATE"
        interpretation = "At least one held-out-offset fold could not train a pooled deployable predictor that passed validation gates."
    elif quality_loss_count:
        result_class = "CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS"
        interpretation = "The pooled cross-offset guardrail is not promoted because at least one held-out offset breached the strict generated-quality loss guardrail."
    elif positive_latency_count == len(heldout_rows) and heldout_rows:
        result_class = "CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_LATENCY_REPLICATED"
        interpretation = "Every held-out offset met latency reduction at equivalent generated quality under the pooled deployable guardrail."
    elif positive_latency_count:
        result_class = "CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_DIRECTIONAL_NOT_PROMOTED"
        interpretation = "Some held-out offsets met the latency endpoint, but the result was not stable enough for promotion."
    else:
        result_class = "CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_INCONCLUSIVE"
        interpretation = "Held-out offsets did not produce a stable latency endpoint and no stronger claim is promoted."
    summary = {
        "suite": "ragwarrant_crag_generative_quality_risk_guardrail_v2",
        "result_class": result_class,
        "interpretation": interpretation,
        "input_artifact_count": len(args.input_roots),
        "offsets": offsets,
        "heldout_offset_count": len(heldout_rows),
        "predictor_gate_passed_count": gate_passed_count,
        "positive_latency_result_count": positive_latency_count,
        "quality_loss_blocked_count": quality_loss_count,
        "primary_endpoint": "latency",
        "governed_winner": V2_POLICY,
        "quality_only_winner": EXPANDED_POLICY,
        "quality_noninferiority_margin": MARGIN,
        "pooled_cross_offset_validation": True,
        "heldout_offset_testing": True,
        "strict_quality_loss_blocking": True,
        "deployable_features_only": True,
        "raw_text_features_used": False,
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
        "secrets_committed": False,
        "heldout_results": heldout_rows,
    }
    write_csv(
        output_root / "pooled_training_rows.csv",
        ["heldout_offset", "training_offset", "example_id", "split", "two_item_quality", "expanded_quality", "label_quality_risk"],
        training_rows,
    )
    write_csv(
        output_root / "predictor_rules.csv",
        [
            "heldout_offset",
            "rule_id",
            "feature_name",
            "operator",
            "threshold",
            "validation_generated_quality_delta_mean",
            "validation_latency_delta_ci_high",
            "validation_unprotected_quality_risk_count",
            "deployable_features_only",
            "raw_text_features_used",
        ],
        predictor_rows,
    )
    write_csv(
        output_root / "heldout_offset_results.csv",
        [
            "heldout_offset",
            "result_class",
            "predictor_result_class",
            "rule_id",
            "feature_name",
            "operator",
            "threshold",
            "example_count",
            "expansion_rate",
            "unprotected_quality_risk_count",
            "generated_quality_delta_mean",
            "generated_quality_delta_ci_low",
            "generated_quality_delta_ci_high",
            "latency_delta_ms_mean",
            "latency_delta_ms_ci_low",
            "latency_delta_ms_ci_high",
            "cost_delta_mean",
            "api_call_delta_mean",
            "quality_loss_blocked",
        ],
        heldout_rows,
    )
    write_json(output_root / "predictor_rules.json", {"rules_evaluated": predictor_rows})
    write_json(output_root / "primary_outcome_statistics.json", summary)
    write_json(output_root / "audit_manifest.json", summary)
    write_json(results_root / "crag_quality_risk_guardrail_v2_comparison.json", summary)
    write_csv(results_root / "crag_quality_risk_guardrail_v2_comparison.csv", list(heldout_rows[0].keys()) if heldout_rows else ["heldout_offset"], heldout_rows)
    report = f"""# CRAG Generative Quality-Risk Guardrail v2

Result class: `{result_class}`

Interpretation: {interpretation}

This v2 guardrail trains candidate expansion rules on pooled validation evidence from other deterministic offsets and evaluates only on held-out offsets. Features are deployable retrieval metrics only. Strict quality-loss blocking prevents promotion if any held-out offset breaches generated-quality noninferiority or leaves quality-risk examples unexpanded.

Raw CRAG questions, raw evidence, raw API responses, raw prompts, raw generated answers, secrets, and private paths are not exported.
"""
    (output_root / "primary_outcome_report.md").write_text(report, encoding="utf-8")
    (results_root / "crag_quality_risk_guardrail_v2_comparison.md").write_text(report, encoding="utf-8")
    print(f"CRAG quality-risk guardrail v2: {result_class}")


if __name__ == "__main__":
    main()
