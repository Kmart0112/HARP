from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import (
    FeatureDefinitionPort,
    FileGatewayPort,
    ParentArtifactPublisherPort,
    TrackingPort,
)
from harp.interface.ports.validation_runner_ports import (
    FeatureValidationMetricsRunnerPort,
    FeatureValidationShapRunnerPort,
    MetricsRunResult,
    ShapReviewResult,
)


@dataclass(frozen=True)
class FeatureToggleSpec:
    feature_name: str
    sections: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True)
class FeatureSetDiffSpec:
    base_feature_set_name: str
    include_features: tuple[str, ...] = ()
    exclude_features: tuple[str, ...] = ()
    include_cat_features: tuple[str, ...] = ()
    exclude_cat_features: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShapReviewSpec:
    candidate_feature: str
    comparison_features: tuple[str, ...]
    validation_mode: str
    report_run_label: str


@dataclass(frozen=True)
class ValidationScenarioSpec:
    scenario_name: str
    toggles: tuple[FeatureToggleSpec, ...]
    validation_mode: str
    feature_set_diff: FeatureSetDiffSpec | None = None
    shap_request: ShapReviewSpec | None = None


@dataclass(frozen=True)
class FeatureDefinitionSpec:
    feature_name: str
    feature_type: str
    change_type: str
    summary: str
    sections: tuple[str, ...]
    comparison_features: tuple[str, ...] = ()
    dbt_model_path: str = ""
    dbt_yaml_path: str = ""
    final_column: str = ""


@dataclass(frozen=True)
class FeatureValidationReportSpec:
    title: str
    background: str
    hypothesis_lines: tuple[str, ...]
    target_features: tuple[FeatureDefinitionSpec, ...]
    leakage_notes: tuple[str, ...]
    implementation_notes: tuple[str, ...]
    metrics_notebook_path: str
    shap_notebook_path: str


@dataclass(frozen=True)
class FeatureValidationRequest:
    validation_name: str
    category: str
    change_summary: str
    experiment_name: str
    preset_name: str
    features_config_path: str
    feature_sets_path: str
    report_out: str
    runs_csv_out: str
    run_log_dir: str
    command: str
    git_commit: str
    resume_parent_run_id: str | None
    scenario_filter: tuple[str, ...]
    finalize: bool
    final_selected_scenario: str | None
    append_note: str | None
    scenarios: tuple[ValidationScenarioSpec, ...]
    report_spec: FeatureValidationReportSpec


@dataclass(frozen=True)
class FeatureValidationDeps:
    file_gateway: FileGatewayPort
    feature_definition_port: FeatureDefinitionPort
    tracking_port: TrackingPort
    parent_artifact_publisher: ParentArtifactPublisherPort
    metrics_runner_port: FeatureValidationMetricsRunnerPort
    shap_runner_port: FeatureValidationShapRunnerPort


@dataclass(frozen=True)
class ValidationScenarioResult:
    scenario_run_id: str
    scenario_name: str
    enabled_features: tuple[str, ...]
    enabled_cat_features: tuple[str, ...]
    features_config_path: str
    metrics_run: MetricsRunResult
    delta_auc: float
    delta_logloss: float
    delta_brier: float
    metrics_judgement: str
    decision: str
    shap_review: ShapReviewResult | None = None


@dataclass(frozen=True)
class FeatureValidationResult:
    validation_name: str
    decision: str
    theme_status: str
    theme_revision: int
    report_path: str
    runs_csv_path: str
    run_log_dir: str
    parent_run_id: str
    scenario_run_ids: dict[str, str]
    effective_scenario_run_ids: dict[str, str]
    new_scenario_run_ids: dict[str, str]
    scenario_results: tuple[ValidationScenarioResult, ...]
    restored_features_state: bool
