from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import (
    FeatureDefinitionPort,
    FileGatewayPort,
    ParentArtifactPublisherPort,
    TrackingPort,
)
from harp.interface.ports.validation_runner_ports import (
    FeatureSelectionMetricsRunnerPort,
    MetricsRunResult,
)


@dataclass(frozen=True)
class AggregateGroupSpec:
    group_id: str
    aggregate_features: tuple[str, ...]
    source_features: tuple[str, ...]


@dataclass(frozen=True)
class VariantGroupSpec:
    group_id: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class FeatureSelectionReportSpec:
    title: str
    background: str
    hypothesis_lines: tuple[str, ...]
    leakage_notes: tuple[str, ...]
    implementation_notes: tuple[str, ...]


@dataclass(frozen=True)
class FeatureSelectionRequest:
    validation_name: str
    category: str
    change_summary: str
    experiment_name: str
    preset_name: str
    feature_sets_path: str
    target_contract_path: str
    report_out: str
    runs_csv_out: str
    decisions_csv_out: str
    selected_contract_snapshot_out: str
    run_log_dir: str
    command: str
    git_commit: str
    resume_parent_run_id: str | None
    scenario_filter: tuple[str, ...]
    finalize: bool
    append_note: str | None
    write_contract: bool
    base_feature_set_name: str
    aggregate_groups: tuple[AggregateGroupSpec, ...]
    variant_groups: tuple[VariantGroupSpec, ...]
    report_spec: FeatureSelectionReportSpec


@dataclass(frozen=True)
class FeatureSelectionDeps:
    file_gateway: FileGatewayPort
    feature_definition_port: FeatureDefinitionPort
    tracking_port: TrackingPort
    parent_artifact_publisher: ParentArtifactPublisherPort
    metrics_runner_port: FeatureSelectionMetricsRunnerPort


@dataclass(frozen=True)
class FeatureSelectionScenarioResult:
    scenario_run_id: str
    scenario_name: str
    phase: str
    group_id: str | None
    tested_set: str
    enabled_features: tuple[str, ...]
    metrics_run: MetricsRunResult
    delta_auc: float
    delta_logloss: float
    delta_brier: float
    metrics_judgement: str


@dataclass(frozen=True)
class FeatureSelectionDecisionRow:
    group_id: str
    decision_type: str
    winner_set: str
    loser_sets: tuple[str, ...]
    reason: str
    delta_auc: float | None
    delta_logloss: float | None
    delta_brier: float | None
    unresolved: bool = False


@dataclass(frozen=True)
class FeatureSelectionResult:
    validation_name: str
    theme_status: str
    theme_revision: int
    report_path: str
    runs_csv_path: str
    decisions_csv_path: str
    selected_contract_snapshot_path: str
    target_contract_path: str
    contract_written: bool
    run_log_dir: str
    parent_run_id: str
    scenario_run_ids: dict[str, str]
    effective_scenario_run_ids: dict[str, str]
    new_scenario_run_ids: dict[str, str]
    scenario_results: tuple[FeatureSelectionScenarioResult, ...]
    decisions: tuple[FeatureSelectionDecisionRow, ...]
