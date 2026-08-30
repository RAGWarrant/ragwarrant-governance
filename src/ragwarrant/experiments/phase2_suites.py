from __future__ import annotations

from pathlib import Path
from typing import Any

from ragwarrant.config import SuiteConfig
from ragwarrant.phase2 import (
    end_to_end_confirmatory_smoke,
    run_challenge_unlock,
    run_data_acquisition,
    run_end_to_end_governance_replay,
    run_human_eval_sample,
    run_robustness_security,
    run_statistical_audit,
)
from ragwarrant.validation_phase3 import (
    run_beneficial_governance_divergence_search_v1,
    run_confirmatory_provenance,
    run_confirmatory_provenance_v2,
    run_confirmatory_readiness_gate_v1,
    run_continued_investment_decision_memo_v1,
    run_crag_acquisition_adapter_v1,
    run_crag_governance_evaluation_v1,
    run_crag_manual_approval_decision_v1,
    run_crag_manual_approval_decision_v2,
    run_crag_mock_api_ablation_v1,
    run_crag_mock_api_case_explanation_pack_v1,
    run_crag_mock_api_docker_reproduction_v1,
    run_crag_mock_api_evidence_synthesis_v1,
    run_crag_mock_api_governance_evaluation_v1,
    run_crag_mock_api_path_v1,
    run_crag_mock_api_repeat_validation_v1,
    run_crag_mock_api_server_smoke_v1,
    run_crag_mock_api_validation_v1,
    run_crag_readiness_gate_v1,
    run_dataset_acquisition_matrix_v2,
    run_dataset_matrix_v3,
    run_dataset_matrix_v4,
    run_end_to_end_governance_replay_v2,
    run_end_to_end_governance_replay_v3,
    run_end_to_end_public_confirmatory_freeze,
    run_end_to_end_public_confirmatory_v2,
    run_end_to_end_public_development,
    run_end_to_end_public_development_v2,
    run_end_to_end_robustness_security_v3,
    run_end_to_end_robustness_v2,
    run_fresh_public_corpus_acquisition_v1,
    run_generative_llm_regime_v1,
    run_generative_llm_validation_v1,
    run_generative_regime_validation_v1,
    run_generator_path_enablement_v2,
    run_generator_path_enablement_v3,
    run_generator_path_enablement_v4,
    run_generator_regime_enablement_v1,
    run_governance_ablation_confirmatory_v1,
    run_governance_ablation_confirmatory_v2,
    run_governance_confirmatory_dataset_v1,
    run_governance_platform_benchmarks_v1,
    run_governance_power_analysis_v2,
    run_governance_robustness_security_confirmatory_v1,
    run_governance_superiority_cases_v1,
    run_governance_workflow_benchmarks_v1,
    run_governed_selection_confirmatory_v1,
    run_governed_selection_confirmatory_v2,
    run_hotpotqa_corpus_reconstruction_v1,
    run_human_eval_execution_readiness_v1,
    run_human_eval_pilot_readiness_v3,
    run_human_eval_pilot_v1,
    run_human_eval_pilot_v4,
    run_human_eval_sample_v2,
    run_human_eval_sample_v3,
    run_human_eval_validation_v1,
    run_human_eval_workflow_setup_v2,
    run_multi_corpus_validation_v1,
    run_multi_corpus_validation_v2,
    run_multi_corpus_validation_v3,
    run_multi_corpus_validation_v4,
    run_multihop_confirmatory_data_verify_v1,
    run_natural_divergence_adjudication_v1,
    run_natural_governance_superiority_v1,
    run_natural_governance_superiority_v2,
    run_natural_governance_superiority_v3,
    run_platform_integration_readiness_v2,
    run_platform_integration_readiness_v3,
    run_power_analysis_v1,
    run_provenance_repair_v1,
    run_public_corpus_acquisition,
    run_public_corpus_expansion,
    run_rag_compass_niche_analysis_v1,
    run_ragbench_end_to_end_loader_v1,
    run_ragbench_subset_expansion_v1,
    run_row_level_reconstruction,
    run_security_regression_v4,
    run_selection_regret_audit_v1,
    run_selection_regret_audit_v2,
    run_strict_git_provenance_repair_v1,
)


def statistical_audit(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_statistical_audit(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def challenge_unlock(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_challenge_unlock(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def data_acquisition(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_data_acquisition(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_confirmatory(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    if cfg.raw.get("confirmatory_freeze"):
        return run_end_to_end_public_confirmatory_freeze(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
    return end_to_end_confirmatory_smoke(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def robustness_security(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_robustness_security(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_governance_replay(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_governance_replay(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_sample(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_human_eval_sample(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def row_level_reconstruction(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_row_level_reconstruction(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def public_corpus_acquisition(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_public_corpus_acquisition(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_public_development(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_public_development(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_governance_replay_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_governance_replay_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_robustness_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_robustness_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def confirmatory_provenance(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_confirmatory_provenance(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def public_corpus_expansion(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_public_corpus_expansion(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_public_development_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_public_development_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def power_analysis_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_power_analysis_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_public_confirmatory_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_public_confirmatory_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_governance_replay_v3(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_governance_replay_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def end_to_end_robustness_security_v3(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_robustness_security_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_sample_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_human_eval_sample_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def confirmatory_provenance_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_confirmatory_provenance_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_confirmatory_dataset_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_confirmatory_dataset_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governed_selection_confirmatory_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governed_selection_confirmatory_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_ablation_confirmatory_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_ablation_confirmatory_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_power_analysis_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_power_analysis_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generative_regime_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generative_regime_validation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_robustness_security_confirmatory_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_robustness_security_confirmatory_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_sample_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_sample_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def provenance_repair_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_provenance_repair_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def fresh_public_corpus_acquisition_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_fresh_public_corpus_acquisition_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def confirmatory_readiness_gate_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_confirmatory_readiness_gate_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governed_selection_confirmatory_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governed_selection_confirmatory_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generator_regime_enablement_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generator_regime_enablement_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_execution_readiness_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_execution_readiness_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def security_regression_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_security_regression_v4(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def strict_git_provenance_repair_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_strict_git_provenance_repair_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def multihop_confirmatory_data_verify_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_multihop_confirmatory_data_verify_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_ablation_confirmatory_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_ablation_confirmatory_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_execution_readiness_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_execution_readiness_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def selection_regret_audit_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_selection_regret_audit_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_superiority_cases_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_superiority_cases_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def multi_corpus_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_multi_corpus_validation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generative_llm_regime_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generative_llm_regime_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_pilot_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_pilot_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_workflow_benchmarks_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_workflow_benchmarks_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def dataset_acquisition_matrix_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_dataset_acquisition_matrix_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def selection_regret_audit_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_selection_regret_audit_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def natural_governance_superiority_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_natural_governance_superiority_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def multi_corpus_validation_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_multi_corpus_validation_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generative_llm_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generative_llm_validation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_validation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def governance_platform_benchmarks_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_governance_platform_benchmarks_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def ragbench_end_to_end_loader_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_ragbench_end_to_end_loader_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def dataset_matrix_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_dataset_matrix_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def multi_corpus_validation_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_multi_corpus_validation_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def natural_governance_superiority_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_natural_governance_superiority_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_manual_approval_decision_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_manual_approval_decision_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generator_path_enablement_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generator_path_enablement_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_workflow_setup_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_workflow_setup_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def platform_integration_readiness_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_platform_integration_readiness_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def hotpotqa_corpus_reconstruction_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_hotpotqa_corpus_reconstruction_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def ragbench_subset_expansion_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_ragbench_subset_expansion_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def dataset_matrix_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_dataset_matrix_v4(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def multi_corpus_validation_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_multi_corpus_validation_v4(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def natural_governance_superiority_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_natural_governance_superiority_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_manual_approval_decision_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_manual_approval_decision_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_acquisition_adapter_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_acquisition_adapter_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_readiness_gate_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_readiness_gate_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_governance_evaluation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_governance_evaluation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_path_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_path_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generator_path_enablement_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generator_path_enablement_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_pilot_readiness_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_pilot_readiness_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def platform_integration_readiness_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_platform_integration_readiness_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def natural_divergence_adjudication_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_natural_divergence_adjudication_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_server_smoke_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_server_smoke_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_governance_evaluation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_governance_evaluation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_validation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_docker_reproduction_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_docker_reproduction_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_ablation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_ablation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_case_explanation_pack_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_case_explanation_pack_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_repeat_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_repeat_validation_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def crag_mock_api_evidence_synthesis_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_crag_mock_api_evidence_synthesis_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def beneficial_governance_divergence_search_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_beneficial_governance_divergence_search_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def rag_compass_niche_analysis_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_rag_compass_niche_analysis_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def generator_path_enablement_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_generator_path_enablement_v4(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def human_eval_pilot_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_human_eval_pilot_v4(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def continued_investment_decision_memo_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    return run_continued_investment_decision_memo_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
