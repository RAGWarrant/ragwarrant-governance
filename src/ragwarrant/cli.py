from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable

from ragwarrant.external_evaluator_adapter_demo import run_external_evaluator_adapter_demo
from ragwarrant.generative_validation_common import write_json, write_md
from ragwarrant.mounted_job_contract import check_mounted_job_contract
from ragwarrant.open_source_arxiv_readiness_synthesis import run_open_source_arxiv_readiness_synthesis
from ragwarrant.promotion_decision import build_promotion_decision, write_promotion_decision
from ragwarrant.public_mini_reproduction import run_public_mini_reproduction
from ragwarrant.rc1_maturity import verify_run
from ragwarrant.selector_ablation_matrix import run_selector_ablation_matrix


ROOT = Path(os.environ.get("RAGWARRANT_REPO_ROOT", Path(__file__).resolve().parents[2]))
EXIT_CONFIG_OR_INPUT_ERROR = 2
EXIT_VALIDATION_GATE_FAILURE = 3
EXIT_RUNTIME_FAILURE = 4


def _output_env() -> str | None:
    return os.environ.get("RAGWARRANT_OUTPUT_DIR") or os.environ.get("RAGWARRANT_OUTPUT_ROOT")


def _input_env() -> str | None:
    return os.environ.get("RAGWARRANT_INPUT_DIR")


def _resolve_output_root(value: str | None, fallback: str) -> Path:
    if value:
        return Path(value)
    if _output_env():
        return Path(str(_output_env()))
    return Path(fallback)


def _resolve_decision_out(value: str | None, output_root: Path) -> Path:
    if value:
        return Path(value)
    return output_root / "promotion_decision.json"


def _resolve_config_path(value: str) -> Path:
    path = Path(value)
    if path.exists() or path.is_absolute():
        return path
    rooted = ROOT / path
    if rooted.exists():
        return rooted
    if _input_env():
        input_path = Path(str(_input_env())) / path
        if input_path.exists():
            return input_path
    return path


def _runtime_validate_bundle() -> int:
    required = [
        ROOT / "configs" / "jobs" / "public_mini_governance_job.yaml",
        ROOT / "schemas" / "promotion_decision.schema.json",
    ]
    forbidden = ["tests", "paper", "docs", "results", "artifacts", "deployment_review"]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.exists()]
    forbidden_present = [name for name in forbidden if (ROOT / name).exists()]
    if missing or forbidden_present:
        payload = {"missing": missing, "forbidden_present": forbidden_present}
        print(f"runtime validation failed: {json.dumps(payload, sort_keys=True)}", file=sys.stderr)
        return EXIT_VALIDATION_GATE_FAILURE
    print("runtime validation passed")
    return 0


def _load_config(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        config: dict[str, object] = {}
        current_list_key: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- ") and current_list_key:
                value = stripped[2:].strip()
                config.setdefault(current_list_key, [])
                assert isinstance(config[current_list_key], list)
                config[current_list_key].append(value)
                continue
            current_list_key = None
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                value = value.strip()
                if value == "":
                    config[key] = []
                    current_list_key = key
                elif value.lower() in {"true", "false"}:
                    config[key] = value.lower() == "true"
                else:
                    config[key] = value.strip("'\"")
        return config
    return yaml.safe_load(text) or {}


def _run_script(args: list[str]) -> int:
    return subprocess.run([sys.executable, *args], cwd=ROOT, check=False).returncode


def cmd_validate_bundle(_args: argparse.Namespace) -> int:
    if os.environ.get("RAGWARRANT_CONTAINER") == "1":
        return _runtime_validate_bundle()
    return _run_script(["scripts/validate_publication_bundle.py"])


def cmd_run_public_mini(args: argparse.Namespace) -> int:
    run_public_mini_reproduction(ROOT, output_root=_resolve_output_root(args.output_root, "artifacts/public_mini_reproduction"))
    return 0


def cmd_run_selector_ablation(args: argparse.Namespace) -> int:
    run_selector_ablation_matrix(ROOT, output_root=_resolve_output_root(args.output_root, "artifacts/selector_ablation_matrix"))
    return 0


def cmd_run_external_evaluator_demo(args: argparse.Namespace) -> int:
    run_external_evaluator_adapter_demo(ROOT, output_root=_resolve_output_root(args.output_root, "artifacts/external_evaluator_adapters"))
    return 0


def cmd_run_claim_check(_args: argparse.Namespace) -> int:
    return cmd_validate_bundle(_args)


def cmd_synthesize_readiness(args: argparse.Namespace) -> int:
    run_open_source_arxiv_readiness_synthesis(ROOT, output_root=_resolve_output_root(args.output_root, "results/open_source_arxiv_readiness"))
    return 0


def cmd_inspect_environment(args: argparse.Namespace) -> int:
    payload = {
        "containerized": os.environ.get("RAGWARRANT_CONTAINER") == "1",
        "cloud_provider_hint": os.environ.get("RAGWARRANT_CLOUD_PROVIDER", "unknown"),
        "python_version": platform.python_version(),
        "os_family": platform.system(),
        "storage_mode": os.environ.get("RAGWARRANT_STORAGE_MODE", "local"),
        "input_dir_configured": bool(_input_env()),
        "output_root_configured": bool(_output_env() or args.output_root),
        "hostnames_exported": False,
        "private_paths_exported": False,
        "secrets_exported": False,
    }
    output_root = _resolve_output_root(args.output_root, "artifacts/environment_inspection")
    if output_root:
        write_json(output_root / "environment_inspection.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_export_decision(args: argparse.Namespace) -> int:
    result_class = args.result_class
    decision = build_promotion_decision(
        run_id=args.run_id,
        suite=args.suite,
        result_class=result_class,
        selected_policy=args.selected_policy,
        baseline_policy=args.baseline_policy,
        artifact_uris=args.artifact_uri,
        validator_status=args.validator_status,
    )
    write_promotion_decision(Path(args.decision_out), decision)
    return 0


def cmd_verify_run(args: argparse.Namespace) -> int:
    result = verify_run(ROOT, run_dir=Path(args.run_dir), output_root=_resolve_output_root(args.output_root, "artifacts/verify_run_demo"))
    return 0 if result["result_class"] == "VERIFY_RUN_PASSED" else 1


def cmd_run_governance_job(args: argparse.Namespace) -> int:
    output_root = _resolve_output_root(args.output_root, "artifacts/public_mini_governance_job")
    decision_out = _resolve_decision_out(args.decision_out, output_root)
    config_path = _resolve_config_path(args.config)
    if not config_path.exists():
        decision = build_promotion_decision(
            run_id="missing_config",
            suite="ragwarrant_governance_job",
            result_class="BLOCK_MISSING_INPUTS",
            decision_reason="job config missing",
            validator_status="not_run",
        )
        write_promotion_decision(decision_out, decision)
        return EXIT_CONFIG_OR_INPUT_ERROR
    config = _load_config(config_path)
    output_root.mkdir(parents=True, exist_ok=True)
    steps = config.get("steps") or ["public_mini_reproduction"]
    artifacts: list[str] = []
    mini_result: dict[str, object] | None = None
    if "public_mini_reproduction" in steps:
        mini_result = run_public_mini_reproduction(
            ROOT,
            output_root=output_root / "public_mini_reproduction",
            write_repository_results=False,
        )
        artifacts.append("public_mini_reproduction/mini_reproduction_manifest.json")
    if "selector_ablation" in steps:
        run_selector_ablation_matrix(ROOT, output_root=output_root / "selector_ablation_matrix")
        artifacts.append("selector_ablation_matrix/selector_ablation_manifest.json")
    validator_status = "not_run"
    validator_rc = 0
    if config.get("run_publication_validator", True):
        validator_rc = cmd_validate_bundle(args)
        validator_status = "passed" if validator_rc == 0 else "failed"
    result_class = str((mini_result or {}).get("result_class", "INCONCLUSIVE"))
    decision = build_promotion_decision(
        run_id=str(config.get("run_id", "public_mini_governance_job")),
        suite=str(config.get("suite", "ragwarrant_cloud_agnostic_governance_job_v1")),
        result_class=result_class,
        selected_policy=str((mini_result or {}).get("governed_winner", "")),
        baseline_policy=str((mini_result or {}).get("quality_only_winner", "")),
        decision_reason="finite governance job completed with sanitized public mini reproduction",
        artifact_uris=artifacts,
        validator_status=validator_status,
        deltas={
            "quality_delta": float((mini_result or {}).get("governed_quality_delta_vs_quality_only", 0.0)),
            "cost_delta": float((mini_result or {}).get("governed_cost_delta_vs_quality_only", 0.0)),
        },
    )
    write_promotion_decision(decision_out, decision)
    write_json(output_root / "run_manifest.json", {"job_config": "<config>", "decision_out": str(decision_out.name), "raw_text_exported": False})
    write_md(output_root / "validation_report.md", f"Governance job decision: `{decision['decision']}`. Validator: `{validator_status}`.")
    write_json(output_root / "validation_report.json", {"validator_status": validator_status, "decision": decision["decision"]})
    return 0 if validator_rc == 0 else EXIT_VALIDATION_GATE_FAILURE


def cmd_check_mounted_contract(args: argparse.Namespace) -> int:
    output_root = _resolve_output_root(args.output_root, "artifacts/mounted_job_contract")
    status, report = check_mounted_job_contract(write_probe=args.force, output_root=output_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragwarrant", description="RAGWarrant governance and promotion-control engine")
    sub = parser.add_subparsers(dest="command", required=False)
    commands: dict[str, Callable[[argparse.Namespace], int]] = {
        "validate-bundle": cmd_validate_bundle,
        "run-public-mini": cmd_run_public_mini,
        "run-selector-ablation": cmd_run_selector_ablation,
        "run-external-evaluator-demo": cmd_run_external_evaluator_demo,
        "run-claim-check": cmd_run_claim_check,
        "synthesize-readiness": cmd_synthesize_readiness,
        "run-governance-job": cmd_run_governance_job,
        "export-decision": cmd_export_decision,
        "inspect-environment": cmd_inspect_environment,
        "verify-run": cmd_verify_run,
        "check-mounted-contract": cmd_check_mounted_contract,
    }
    for name, func in commands.items():
        child = sub.add_parser(name)
        child.set_defaults(func=func)
        child.add_argument("--config", default="configs/jobs/public_mini_governance_job.yaml")
        child.add_argument("--output-root", default=None)
        child.add_argument("--decision-out", default=None)
        child.add_argument("--force", action="store_true")
    verify = sub.choices["verify-run"]
    verify.add_argument("--run-dir", default="artifacts/public_mini_reproduction")
    export = sub.choices["export-decision"]
    export.add_argument("--run-id", default="manual_export")
    export.add_argument("--suite", default="manual")
    export.add_argument("--result-class", default="INCONCLUSIVE")
    export.add_argument("--selected-policy", default="")
    export.add_argument("--baseline-policy", default="")
    export.add_argument("--artifact-uri", action="append", default=[])
    export.add_argument("--validator-status", default="not_run")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
