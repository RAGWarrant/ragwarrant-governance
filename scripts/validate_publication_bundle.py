#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_ROOT = Path(os.environ["EXPORT_ROOT"]).resolve() if os.environ.get("EXPORT_ROOT") else ROOT.parent

REQUIRED = [
    "README.md",
    "LICENSE",
    "CITATION.cff",
    "docs/claim_boundaries.md",
    "data/DATA_AVAILABILITY.md",
    "results/run_index.csv",
    "results/evidence_summary.json",
    "results/claim_status/claim_status_table.csv",
    ".gitattributes",
    "artifacts/fresh_live_crag_behavioral_governance/live_crag_manifest.json",
    "artifacts/hotpotqa_behavioral_governance/hotpotqa_acquisition_manifest.json",
    "results/multi_dataset_behavioral_governance/synthesis_result.json",
    "docs/fresh_live_crag_hotpotqa_behavioral_governance_plan.md",
    "docs/dataset_acquisition.md",
    "artifacts/generative_llm_validation/crag/generative_crag_manifest.json",
    "artifacts/generative_llm_validation/hotpotqa/generative_hotpotqa_manifest.json",
    "results/generative_llm_validation/synthesis_result.json",
    "docs/generative_llm_validation.md",
    "docs/generator_configuration.md",
    "docs/platform_benchmarking_boundary.md",
    "configs/experiments/ragwarrant_hotpotqa_generative_quality_signal_audit_v1.yaml",
    "configs/experiments/ragwarrant_crag_generative_quality_risk_guardrail_v2.yaml",
    "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json",
    "artifacts/generative_llm_validation/crag_quality_risk_guardrail_v2/audit_manifest.json",
    "results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.json",
    "deployment_review/generative_llm_validation_quality_signal_audit/generator_access_diagnosis.json",
    "configs/experiments/ragwarrant_public_mini_reproduction_v1.yaml",
    "artifacts/public_mini_reproduction/mini_reproduction_manifest.json",
    "results/public_mini_reproduction/claim_update.json",
    "docs/quickstart.md",
    "docs/public_mini_reproduction.md",
    "configs/experiments/ragwarrant_crag_generated_answer_evaluator_mapping_v1.yaml",
    "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json",
    "docs/crag_generated_answer_evaluator_mapping.md",
    "configs/experiments/ragwarrant_external_evaluator_adapter_demo_v1.yaml",
    "artifacts/external_evaluator_adapters/external_evaluator_manifest.json",
    "docs/external_evaluator_adapters.md",
    "configs/experiments/ragwarrant_selector_ablation_matrix_v1.yaml",
    "artifacts/selector_ablation_matrix/selector_ablation_manifest.json",
    "docs/selector_ablation_matrix.md",
    "configs/experiments/ragwarrant_aim_hardware_characterization_v1.yaml",
    "artifacts/aim_hardware_characterization/hardware_manifest.json",
    "docs/aim_hardware_characterization.md",
    "configs/experiments/ragwarrant_open_source_arxiv_readiness_synthesis_v1.yaml",
    "results/open_source_arxiv_readiness/synthesis_result.json",
    "docs/open_source_arxiv_readiness.md",
    "Dockerfile",
    ".dockerignore",
    "src/ragwarrant/cli.py",
    "src/ragwarrant/promotion_decision.py",
    "src/ragwarrant/storage/factory.py",
    "src/ragwarrant/deployment_readiness.py",
    "scripts/validate_deployment_readiness.py",
    "configs/jobs/public_mini_governance_job.yaml",
    "configs/experiments/ragwarrant_deployment_readiness_v1.yaml",
    "schemas/promotion_decision.schema.json",
    "schemas/run_manifest.schema.json",
    "schemas/deployment_readiness.schema.json",
    "docs/product_contract.md",
    "docs/deployment_architecture.md",
    "docs/operator_workflow.md",
    "docs/cloud_agnostic_deployment.md",
    "docs/artifact_storage.md",
    "docs/promotion_decision_schema.md",
    "deploy/kubernetes/ragwarrant-job.yaml",
    "deploy/kubernetes/ragwarrant-cronjob.yaml",
    "deploy/azure/container-apps-job.bicep",
    "deploy/aws/ecs-fargate-task.json",
    "deploy/aws/batch-job-definition.json",
    "deploy/gcp/cloud-run-job.yaml",
    "deploy/github-actions/validate-docker.yml",
    "artifacts/deployment_readiness/deployment_readiness_manifest.json",
    "artifacts/deployment_readiness/promotion_decision.json",
    "results/deployment_readiness/claim_update.json",
    "docker-compose.yml",
    "docker/compose.public-mini.yml",
    "docs/docker_runtime_validation.md",
    "docs/container_security_scans.md",
    "scripts/diagnose_container_runtime.py",
    "scripts/validate_docker_static.py",
    "scripts/run_container_smoke_tests.py",
    "scripts/run_optional_container_security_scans.py",
    "configs/experiments/ragwarrant_container_smoke_tests_v1.yaml",
    "artifacts/docker_hardening/container_runtime_diagnostics.json",
    "artifacts/docker_hardening/docker_static_validation.json",
    "artifacts/docker_hardening/container_smoke_test_manifest.json",
    "artifacts/docker_hardening/container_security_scan_manifest.json",
    "results/docker_hardening/claim_update.json",
    "docs/docker_runtime_validation.md",
    "configs/experiments/ragwarrant_fresh_clone_reproducibility_v1.yaml",
    "artifacts/fresh_clone_reproducibility/fresh_clone_manifest.json",
    "results/fresh_clone_reproducibility/claim_update.json",
    "docs/fresh_clone_reproducibility.md",
    "configs/experiments/ragwarrant_release_candidate_v1.yaml",
    "artifacts/release_candidate/v0.1.0-rc1/release_candidate_manifest.json",
    "artifacts/release_candidate/v0.1.0-rc1/release_checksums.sha256",
    "docs/release_process.md",
    "docs/release_notes_v0.1.0-rc1.md",
    "configs/experiments/ragwarrant_crag_evaluator_mapping_diagnostic_v2.yaml",
    "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json",
    "docs/crag_evaluator_mapping_v2.md",
    "configs/experiments/ragwarrant_hotpotqa_generative_quality_signal_audit_v2.yaml",
    "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json",
    "docs/hotpotqa_quality_signal_audit_v2.md",
    "configs/experiments/ragwarrant_selector_ablation_stress_v2.yaml",
    "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json",
    "docs/selector_ablation_stress_v2.md",
    "schemas/artifact_manifest.schema.json",
    "artifacts/verify_run_demo/verify_run_manifest.json",
    "docs/artifact_integrity.md",
    "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json",
    "docs/external_evaluator_adapters.md",
    "configs/experiments/ragwarrant_aim_hardware_matrix_v1.yaml",
    "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json",
    "docs/aim_hardware_matrix.md",
    "docs/arxiv_paper_plan.md",
    "docs/arxiv_reproducibility_appendix.md",
    "paper/main.tex",
    "paper/tables/result_taxonomy_table.tex",
    "paper/tables/claim_boundary_table.tex",
    "paper/tables/selector_ablation_summary.tex",
    "paper/tables/deployment_readiness_table.tex",
    "paper/tables/reproducibility_table.tex",
    "configs/experiments/ragwarrant_rc1_arxiv_readiness_synthesis_v1.yaml",
    "results/rc1_arxiv_readiness/synthesis_result.json",
]

EXPORT_REQUIRED = [
    "approval_package/approval_request_summary.md",
    "approval_package/publication_safety_audit.md",
    "approval_package/publication_safety_audit.json",
    "approval_package/data_license_audit.md",
    "approval_package/upload_blocker_record.md",
    "approval_package/github_upload_commands_NOT_RUN.md",
    "validation_reports/secret_scan_report.md",
    "validation_reports/secret_scan_report.json",
]

ALLOWED_PUBLIC_REPOSITORY_REMOTES = {
    "https://github.com/RAGWarrant/ragwarrant-governance",
    "https://github.com/RAGWarrant/ragwarrant-governance.git",
    "git@github.com:RAGWarrant/ragwarrant-governance",
    "git@github.com:RAGWarrant/ragwarrant-governance.git",
    "https://github.com/RAGWarrant/ragwarrant-governance-public",
    "https://github.com/RAGWarrant/ragwarrant-governance-public.git",
    "git@github.com:RAGWarrant/ragwarrant-governance-public",
    "git@github.com:RAGWarrant/ragwarrant-governance-public.git",
}

SECRET_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"\b(?:ghp|github_pat|gho)_[A-Za-z0-9_]{20,}"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{30,}", re.I),
}

FORBIDDEN_TRACKED_PARTS = {
    ".env",
    "data/raw",
    "results/raw/crag",
    "artifacts/raw",
    "human_eval_answer_key_private.json",
}

MAX_FILE_BYTES = 50 * 1024 * 1024

CRAG_ARTIFACT_ROOT = Path("artifacts/selected_run_summaries")
RAW_TEXT_JSON_KEYS = {
    "query_text",
    "question_text",
    "raw_query",
    "raw_question",
    "source_snippet",
    "raw_response",
    "api_response",
    "document_text",
    "context_text",
    "snippet",
    "generated_answer",
    "generated_answer_text",
    "answer_text",
    "raw_answer",
    "prompt_text",
}
GENERATIVE_ARTIFACT_ROOT = Path("artifacts/generative_llm_validation")


def tracked_files() -> list[Path]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    except Exception:
        excluded_parts = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
        return [p.relative_to(ROOT) for p in ROOT.rglob("*") if p.is_file() and not (excluded_parts & set(p.parts))]
    return [Path(line) for line in out.splitlines() if line.strip()]


def fail(message: str) -> None:
    print(f"publication validation failed: {message}", file=sys.stderr)
    sys.exit(1)


def approved_deployment_remote() -> str | None:
    report_path = ROOT / "deployment_review" / "reports" / "github_deployment_report.json"
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if report.get("deployment_status") != "DEPLOYED":
        return None
    if report.get("environment_allows_github") != "PASS_AFTER_EXPLICIT_USER_APPROVAL":
        return None
    return report.get("remote_url")


def publication_remote_mode() -> str:
    explicit = os.environ.get("RAGWARRANT_PUBLICATION_REMOTE_MODE")
    if explicit:
        return explicit
    if os.environ.get("GITHUB_ACTIONS") == "true":
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        if repository == "RAGWarrant/ragwarrant-governance":
            return "github_actions_public_repo"
        return "github_actions_unapproved_repo"
    return "deployed_public_repo"


def normalize_remote_line(line: str) -> str:
    for suffix in (" (fetch)", " (push)"):
        line = line.replace(suffix, "")
    if "\t" in line:
        line = line.split("\t", 1)[1]
    return line.strip()


def public_repository_remote_allowed(remotes: str) -> bool:
    """Allow the approved public clean-history repository in deployed mode.

    Local unpublished export packages still reject external remotes. The
    public repository is intentionally different: it is already deployed, has
    a fresh one-commit history, and carries a public repository note. GitHub
    Actions mode is allowed only for the expected public repository slug.
    """

    mode = publication_remote_mode()
    if mode in {"local_unpublished", "github_actions_unapproved_repo"}:
        return False
    if mode not in {"deployed_public_repo", "github_actions_public_repo"}:
        return False
    remote_lines = [normalize_remote_line(line) for line in remotes.splitlines() if line.strip()]
    if not remote_lines:
        return False
    public_note = ROOT / "docs" / "public_repository_note.md"
    if not public_note.exists():
        return False
    return all(line in ALLOWED_PUBLIC_REPOSITORY_REMOTES for line in remote_lines)


def validate_no_crag_raw_text_fields() -> None:
    root = ROOT / CRAG_ARTIFACT_ROOT
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        lower_name = path.name.lower()
        if path.suffix.lower() == ".csv" and "crag" in rel.lower():
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames or []
            raw_fields = [field for field in fieldnames if field.lower() in RAW_TEXT_JSON_KEYS]
            if raw_fields:
                fail(f"raw CRAG text field(s) in {rel}: {raw_fields}")
        elif path.suffix.lower() == ".json" and "crag" in rel.lower():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            hits: list[str] = []

            def walk(value: object, prefix: str = "") -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        child_path = f"{prefix}.{key}" if prefix else key
                        if key.lower() in RAW_TEXT_JSON_KEYS:
                            hits.append(child_path)
                        walk(child, child_path)
                elif isinstance(value, list):
                    for idx, child in enumerate(value):
                        walk(child, f"{prefix}[{idx}]")

            walk(payload)
            if hits:
                fail(f"raw CRAG text key(s) in {rel}: {hits[:5]}")
        elif path.suffix.lower() == ".md" and "crag" in rel.lower() and ("case" in lower_name or "pack" in lower_name):
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?im)^\\s*-?\\s*Query:\\s*\\S", text):
                fail(f"raw CRAG query line in {rel}")


def validate_generative_artifacts() -> None:
    synthesis_path = ROOT / "results/generative_llm_validation/synthesis_result.json"
    if not synthesis_path.exists():
        fail("missing generative validation synthesis result")
    synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    result_class = str(synthesis.get("result_class", ""))
    allowed = {
        "GEN_LLM_SYNTHESIS_GENERATIVE_VALIDATION_SUPPORTED",
        "GEN_LLM_SYNTHESIS_DIRECTIONAL",
        "GEN_LLM_SYNTHESIS_MIXED",
        "GEN_LLM_SYNTHESIS_INCONCLUSIVE",
        "GEN_LLM_SYNTHESIS_BLOCKED",
        "GEN_LLM_SYNTHESIS_NEGATIVE",
    }
    if result_class not in allowed:
        fail(f"unknown generative synthesis result class: {result_class}")
    root = ROOT / GENERATIVE_ARTIFACT_ROOT
    if not root.exists():
        fail("missing generative validation artifact root")
    positive_result_classes = {
        "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY",
        "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY",
        "GEN_LLM_GOVERNANCE_IMPROVES_GENERATED_QUALITY_UNDER_FIXED_BUDGET",
        "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
        "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
        "GEN_LLM_GOVERNANCE_IMPROVES_GENERATED_QUALITY_UNDER_FIXED_BUDGET_CRAG",
    }
    forbidden_keys = {"prompt_text", "generated_answer", "generated_answer_text", "answer_text", "raw_answer"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".csv"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            hits: list[str] = []

            def walk(value: object, prefix: str = "") -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        child_path = f"{prefix}.{key}" if prefix else key
                        if key.lower() in forbidden_keys:
                            hits.append(child_path)
                        walk(child, child_path)
                elif isinstance(value, list):
                    for idx, child in enumerate(value):
                        walk(child, f"{prefix}[{idx}]")

            walk(payload)
            if hits:
                fail(f"raw generative text key(s) in {rel}: {hits[:5]}")
            if path.name == "primary_outcome_statistics.json":
                result = str(payload.get("result_class", ""))
                if result in positive_result_classes:
                    if not payload.get("usable_quality_signal", False):
                        fail(f"positive generated-governance result lacks usable quality signal in {rel}")
                    if int(payload.get("non_empty_generated_answers", 0)) <= 0:
                        fail(f"positive generated-governance result has no nonempty generated answers in {rel}")
                    if int(payload.get("unique_answer_hash_count", 0)) <= 1:
                        fail(f"positive generated-governance result lacks answer-hash diversity in {rel}")
        elif path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                fieldnames = csv.DictReader(handle).fieldnames or []
            raw_fields = [field for field in fieldnames if field.lower() in forbidden_keys]
            if raw_fields:
                fail(f"raw generated-answer field(s) in {rel}: {raw_fields}")
    audit_manifest = ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json"
    if audit_manifest.exists():
        audit = json.loads(audit_manifest.read_text(encoding="utf-8"))
        if "zero" in str(audit.get("prior_zero_delta_explanation", "")).lower() and not audit.get("result_class"):
            fail("HotpotQA quality-signal audit lacks a machine-readable result class")
    guardrail_v2_path = ROOT / "results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.json"
    if guardrail_v2_path.exists():
        guardrail_v2 = json.loads(guardrail_v2_path.read_text(encoding="utf-8"))
        if not guardrail_v2.get("pooled_cross_offset_validation"):
            fail("CRAG quality-risk guardrail v2 lacks pooled cross-offset validation")
        if not guardrail_v2.get("heldout_offset_testing"):
            fail("CRAG quality-risk guardrail v2 lacks held-out-offset testing")
        if not guardrail_v2.get("deployable_features_only"):
            fail("CRAG quality-risk guardrail v2 does not declare deployable-only features")
        if guardrail_v2.get("raw_text_features_used"):
            fail("CRAG quality-risk guardrail v2 used raw text features")
        if guardrail_v2.get("raw_prompts_committed") or guardrail_v2.get("raw_generated_answers_committed"):
            fail("CRAG quality-risk guardrail v2 committed raw prompt or generated-answer text")
        if int(guardrail_v2.get("quality_loss_blocked_count", 0)) > 0:
            blocked_class = "CRAG_GEN_LLM_QUALITY_RISK_GUARDRAIL_V2_BLOCKED_HELDOUT_QUALITY_LOSS"
            if guardrail_v2.get("result_class") != blocked_class:
                fail("CRAG quality-risk guardrail v2 did not block promotion after held-out quality loss")
    docs_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in [
            ROOT / "docs/generative_llm_validation.md",
            ROOT / "docs/platform_benchmarking_boundary.md",
        ]
        if path.exists()
    )
    if "official platform benchmarking completed" in docs_text:
        fail("local or hosted generative validation is described as official platform benchmarking")


def validate_open_source_readiness_artifacts() -> None:
    mini = json.loads((ROOT / "artifacts/public_mini_reproduction/mini_reproduction_manifest.json").read_text(encoding="utf-8"))
    if mini.get("raw_external_data_used") or mini.get("raw_text_exported"):
        fail("public mini reproduction exported raw external data or text")
    if mini.get("result_class") not in {
        "PUBLIC_MINI_REPRODUCTION_PASSED",
        "PUBLIC_MINI_REPRODUCTION_GOVERNANCE_PROMOTES_SAFE_POLICY",
        "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED",
        "PUBLIC_MINI_REPRODUCTION_INCONCLUSIVE",
        "PUBLIC_MINI_REPRODUCTION_BLOCKED",
    }:
        fail("public mini reproduction has unknown result class")
    crag_mapping = json.loads((ROOT / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json").read_text(encoding="utf-8"))
    if crag_mapping.get("raw_crag_text_committed") or crag_mapping.get("raw_generated_answers_committed"):
        fail("CRAG evaluator mapping committed raw text")
    external = json.loads((ROOT / "artifacts/external_evaluator_adapters/external_evaluator_manifest.json").read_text(encoding="utf-8"))
    if external.get("tool_replacement_claimed"):
        fail("external evaluator adapter claims to replace evaluator tools")
    selector = json.loads((ROOT / "artifacts/selector_ablation_matrix/selector_ablation_manifest.json").read_text(encoding="utf-8"))
    if selector.get("universal_superiority_claimed"):
        fail("selector ablation claims universal superiority")
    hardware = json.loads((ROOT / "artifacts/aim_hardware_characterization/hardware_manifest.json").read_text(encoding="utf-8"))
    if hardware.get("official_platform_benchmark"):
        fail("AIM hardware characterization claims official platform benchmark")
    if hardware.get("private_paths_exported") or hardware.get("hostnames_exported") or hardware.get("ip_addresses_exported"):
        fail("AIM hardware characterization exported private machine details")
    readiness = json.loads((ROOT / "results/open_source_arxiv_readiness/synthesis_result.json").read_text(encoding="utf-8"))
    if readiness.get("result_class") not in {
        "OPEN_SOURCE_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES",
        "OPEN_SOURCE_ARXIV_READINESS_DIRECTIONAL",
        "OPEN_SOURCE_ARXIV_READINESS_MIXED",
        "OPEN_SOURCE_ARXIV_READINESS_INCONCLUSIVE",
        "OPEN_SOURCE_ARXIV_READINESS_BLOCKED",
    }:
        fail("open-source/arXiv readiness synthesis has unknown result class")
    if not readiness.get("does_not_claim_rag_compass_superiority"):
        fail("readiness synthesis does not preserve RAG Compass claim boundary")


def validate_deployment_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for required in [".git", ".local_data", ".env", "*.pem", "*.key", "*.onnx", "*.ckpt", "artifacts/**/raw*", "results/**/raw*"]:
        if required not in dockerignore:
            fail(f".dockerignore does not exclude {required}")
    manifest = json.loads((ROOT / "artifacts/deployment_readiness/deployment_readiness_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("result_class") not in {
        "DEPLOYMENT_READINESS_SUPPORTED_WITH_BOUNDARIES",
        "DEPLOYMENT_READINESS_BLOCKED_PUBLICATION_HYGIENE",
    }:
        fail("deployment readiness manifest has unknown result class")
    if manifest.get("official_platform_benchmarking_claimed"):
        fail("deployment readiness claims official platform benchmarking")
    if manifest.get("production_readiness_claimed"):
        fail("deployment readiness claims production operation")
    if manifest.get("raw_data_committed") or manifest.get("raw_prompts_committed") or manifest.get("raw_generated_answers_committed"):
        fail("deployment readiness artifacts indicate raw text was committed")
    decision = json.loads((ROOT / "artifacts/deployment_readiness/promotion_decision.json").read_text(encoding="utf-8"))
    if decision.get("decision") not in {"PROMOTE", "BLOCK", "REJECT", "INCONCLUSIVE", "ERROR"}:
        fail("deployment promotion decision has invalid decision")
    boundaries = decision.get("claim_boundaries", {})
    if boundaries.get("official_platform_benchmarking_claimed") or boundaries.get("production_readiness_claimed"):
        fail("deployment promotion decision violates claim boundaries")
    docs_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in [
            ROOT / "docs/product_contract.md",
            ROOT / "docs/deployment_architecture.md",
            ROOT / "docs/cloud_agnostic_deployment.md",
            ROOT / "docs/operator_workflow.md",
            ROOT / "docs/docker_runtime_validation.md",
            ROOT / "docker/README.md",
        ]
    )
    if "official platform benchmarking completed" in docs_text:
        fail("deployment docs claim official platform benchmarking")
    if "validated in production" in docs_text:
        fail("deployment docs claim production validation")
    static = json.loads((ROOT / "artifacts/docker_hardening/docker_static_validation.json").read_text(encoding="utf-8"))
    if static.get("result_class") != "DOCKER_STATIC_VALIDATION_PASSED":
        fail("Docker static validation did not pass")
    runtime = json.loads((ROOT / "artifacts/docker_hardening/container_runtime_diagnostics.json").read_text(encoding="utf-8"))
    if runtime.get("private_paths_exported") or runtime.get("secrets_exported"):
        fail("container runtime diagnostics exported private paths or secrets")
    smoke = json.loads((ROOT / "artifacts/docker_hardening/container_smoke_test_manifest.json").read_text(encoding="utf-8"))
    allowed_smoke = {
        "DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
        "PODMAN_RUNTIME_VALIDATED_PUBLIC_MINI",
        "COLIMA_DOCKER_RUNTIME_VALIDATED_PUBLIC_MINI",
        "CONTAINER_RUNTIME_STATIC_VALIDATION_ONLY",
        "CONTAINER_RUNTIME_VALIDATION_SKIPPED_DAEMON_UNAVAILABLE",
        "CONTAINER_RUNTIME_VALIDATION_SKIPPED_ENGINE_UNAVAILABLE",
        "CONTAINER_RUNTIME_VALIDATION_FAILED",
        "CONTAINER_RUNTIME_VALIDATION_FAILED_PUBLICATION_HYGIENE",
    }
    if smoke.get("result_class") not in allowed_smoke:
        fail("unknown container smoke-test result class")
    if "SKIPPED" in str(smoke.get("result_class")) and not smoke.get("skip_reason"):
        fail("container runtime skip lacks explicit reason")
    if smoke.get("live_cloud_validation_claimed") or smoke.get("production_readiness_claimed") or smoke.get("official_platform_benchmarking_claimed"):
        fail("container smoke test overclaims deployment status")
    security = json.loads((ROOT / "artifacts/docker_hardening/container_security_scan_manifest.json").read_text(encoding="utf-8"))
    allowed_security = {
        "CONTAINER_SECURITY_SCANS_COMPLETED",
        "CONTAINER_SECURITY_SCANS_PARTIAL",
        "CONTAINER_SECURITY_SCANS_SKIPPED_TOOLS_UNAVAILABLE",
        "CONTAINER_SECURITY_SCANS_SKIPPED_IMAGE_UNAVAILABLE",
        "CONTAINER_SECURITY_SCANS_FAILED_CRITICAL_FINDINGS",
    }
    if security.get("result_class") not in allowed_security:
        fail("unknown container security-scan result class")
    for helper in ["docker/run_public_mini.sh", "docker/run_governance_job.sh", "docker/healthcheck.sh"]:
        if not os.access(ROOT / helper, os.X_OK):
            fail(f"Docker helper script is not executable: {helper}")


def validate_rc1_arxiv_readiness_artifacts() -> None:
    allowed = {
        "fresh_clone": {
            "FRESH_CLONE_REPRODUCTION_PASSED_GIT_CLONE",
            "FRESH_CLONE_REPRODUCTION_PASSED_LOCAL_COPY",
            "FRESH_CLONE_REPRODUCTION_PARTIAL",
            "FRESH_CLONE_REPRODUCTION_BLOCKED_NETWORK",
            "FRESH_CLONE_REPRODUCTION_BLOCKED_INSTALL",
            "FRESH_CLONE_REPRODUCTION_BLOCKED_VALIDATION",
            "FRESH_CLONE_REPRODUCTION_FAILED",
        },
        "release_candidate": {
            "RELEASE_CANDIDATE_READY",
            "RELEASE_CANDIDATE_PARTIAL",
            "RELEASE_CANDIDATE_BLOCKED_VALIDATION",
            "RELEASE_CANDIDATE_BLOCKED_HYGIENE",
            "RELEASE_CANDIDATE_BLOCKED_MISSING_ARTIFACTS",
        },
        "crag_mapping_v2": {
            "CRAG_EVALUATOR_MAPPING_V2_ACTIVE_NONCONSTANT_SIGNAL",
            "CRAG_EVALUATOR_MAPPING_V2_PARTIAL",
            "CRAG_EVALUATOR_MAPPING_V2_PROXY_ONLY",
            "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_CRAG_DATA",
            "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_EVALUATOR",
            "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_SCHEMA_MAPPING",
            "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_USABLE_SIGNAL",
            "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_PUBLICATION_HYGIENE",
        },
        "hotpotqa_audit_v2": {
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_CONFIRMED_NONCONSTANT_SIGNAL",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_TRUE_EQUIVALENCE",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_SCORER_ISSUE_FOUND",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_GENERATOR_INSENSITIVE",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_QUALITY_LOSS",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_INCONCLUSIVE",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_NO_GENERATOR",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_NO_DATA",
            "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_PUBLICATION_HYGIENE",
        },
        "selector_stress_v2": {
            "SELECTOR_ABLATION_STRESS_V2_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS",
            "SELECTOR_ABLATION_STRESS_V2_GOVERNANCE_NOT_SUPERIOR",
            "SELECTOR_ABLATION_STRESS_V2_MIXED",
            "SELECTOR_ABLATION_STRESS_V2_INCONCLUSIVE",
            "SELECTOR_ABLATION_STRESS_V2_BLOCKED_INSUFFICIENT_INPUTS",
        },
        "verify_run": {
            "VERIFY_RUN_PASSED",
            "VERIFY_RUN_FAILED_MISSING_ARTIFACT",
            "VERIFY_RUN_FAILED_HASH_MISMATCH",
            "VERIFY_RUN_FAILED_SCHEMA",
            "VERIFY_RUN_FAILED_PUBLICATION_HYGIENE",
            "VERIFY_RUN_INCONCLUSIVE",
        },
        "external_v2": {
            "EXTERNAL_EVALUATOR_ADAPTER_V2_DEMO_PASSED",
            "EXTERNAL_EVALUATOR_ADAPTER_V2_PROMOTION_DECISION_GENERATED",
            "EXTERNAL_EVALUATOR_ADAPTER_V2_BLOCKED_INVALID_SCHEMA",
            "EXTERNAL_EVALUATOR_ADAPTER_V2_BLOCKED_NO_METRICS",
            "EXTERNAL_EVALUATOR_ADAPTER_V2_BLOCKED_PUBLICATION_HYGIENE",
        },
        "hardware_matrix": {
            "AIM_HARDWARE_MATRIX_COMPLETED",
            "AIM_HARDWARE_MATRIX_PARTIAL",
            "AIM_HARDWARE_MATRIX_BLOCKED",
        },
        "rc1_synthesis": {
            "RC1_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES",
            "RC1_ARXIV_READINESS_DIRECTIONAL",
            "RC1_ARXIV_READINESS_MIXED",
            "RC1_ARXIV_READINESS_INCONCLUSIVE",
            "RC1_ARXIV_READINESS_BLOCKED",
        },
    }
    paths = {
        "fresh_clone": ROOT / "artifacts/fresh_clone_reproducibility/fresh_clone_manifest.json",
        "release_candidate": ROOT / "artifacts/release_candidate/v0.1.0-rc1/release_candidate_manifest.json",
        "crag_mapping_v2": ROOT / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json",
        "hotpotqa_audit_v2": ROOT / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json",
        "selector_stress_v2": ROOT / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json",
        "verify_run": ROOT / "artifacts/verify_run_demo/verify_run_manifest.json",
        "external_v2": ROOT / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json",
        "hardware_matrix": ROOT / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json",
        "rc1_synthesis": ROOT / "results/rc1_arxiv_readiness/synthesis_result.json",
    }
    for key, path in paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("result_class") not in allowed[key]:
            fail(f"unknown RC1 result class for {key}: {payload.get('result_class')}")
    if json.loads(paths["external_v2"].read_text(encoding="utf-8")).get("tool_replacement_claimed"):
        fail("external evaluator adapters v2 claim tool replacement")
    hardware = json.loads(paths["hardware_matrix"].read_text(encoding="utf-8"))
    if hardware.get("official_platform_benchmark") or hardware.get("hostnames_exported") or hardware.get("private_paths_exported"):
        fail("AIM hardware matrix violates publication boundaries")
    crag = json.loads(paths["crag_mapping_v2"].read_text(encoding="utf-8"))
    if crag.get("raw_crag_text_committed") or crag.get("raw_generated_answers_committed"):
        fail("CRAG evaluator mapping v2 committed raw text")
    paper = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    for section in ["Problem Statement", "Governance Model", "Claim-Boundary Validation", "External Evaluator Adapter Architecture", "AIM Hardware Characterization"]:
        if section not in paper:
            fail(f"paper draft missing section: {section}")
    forbidden = ["RAG Compass is proven superior", "production validated", "official platform benchmark completed", "human evaluation completed"]
    for phrase in forbidden:
        if phrase.lower() in paper.lower():
            fail(f"paper draft contains unsupported claim phrase: {phrase}")


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        fail(f"missing required files: {missing}")
    export_missing = [path for path in EXPORT_REQUIRED if not (EXPORT_ROOT / path).exists()]
    if export_missing and os.environ.get("EXPORT_ROOT"):
        fail(f"missing export approval files: {export_missing}")

    files = tracked_files()
    for rel in files:
        rel_text = rel.as_posix()
        if any(part in rel_text for part in FORBIDDEN_TRACKED_PARTS):
            fail(f"forbidden tracked path: {rel_text}")
        path = ROOT / rel
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
            fail(f"file exceeds 50 MB threshold: {rel_text}")
        if path.is_file() and path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".pdf"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    fail(f"secret-like pattern {label} in {rel_text}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    forbidden_claims = [
        "rag compass is proven superior",
        "production validated",
        "human evaluation completed",
        "generative llm validation completed",
        "official platform benchmark completed",
    ]
    for claim in forbidden_claims:
        if claim in readme:
            fail(f"unsupported claim found in README: {claim}")

    summary = json.loads((ROOT / "results/evidence_summary.json").read_text(encoding="utf-8"))
    if "unsupported_claims" not in summary:
        fail("evidence summary lacks unsupported_claims")

    validate_no_crag_raw_text_fields()
    validate_generative_artifacts()
    validate_open_source_readiness_artifacts()
    validate_deployment_artifacts()
    validate_rc1_arxiv_readiness_artifacts()

    try:
        remotes = subprocess.check_output(["git", "remote", "-v"], cwd=ROOT, text=True)
    except Exception:
        remotes = ""
    if remotes.strip():
        approved_remote = approved_deployment_remote()
        approved = "approved-internal-git-url" in remotes
        if approved_remote:
            remote_lines = [line for line in remotes.splitlines() if line.strip()]
            approved = approved or all(approved_remote in line for line in remote_lines)
        approved = approved or public_repository_remote_allowed(remotes)
        if not approved:
            fail("external git remote configured in publication bundle")

    print("publication validation passed")


if __name__ == "__main__":
    main()
