from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MetricsRunResult:
    scenario_name: str
    timestamp: str
    auc: float
    logloss: float
    brier: float
    artifact_path: str
    manifest_path: str
    log_path: str
    artifact_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShapReviewResult:
    scenario_name: str
    candidate_feature: str
    metrics_judgement: str
    shap_judgement: str
    final_recommendation: str
    official_report_path: str
    official_report_source_path: str
    summary_json_path: str
    manifest_json_path: str
    artifact_bundle_dir: str
    artifact_report_path: str
    candidate_dependence_path: str
    candidate_dependence_source_path: str
    global_rank: str
    mean_abs_shap: str
    importance_share: str
    log_path: str
    artifact_paths: tuple[str, ...] = ()


class FeatureValidationMetricsRunnerPort(Protocol):
    def run_metrics(
        self,
        *,
        scenario_name: str,
        run_log_dir: str,
        features_config_path: str,
    ) -> MetricsRunResult:
        ...


class FeatureSelectionMetricsRunnerPort(Protocol):
    def run_metrics(
        self,
        *,
        scenario_name: str,
        run_log_dir: str,
        features_config_path: str,
    ) -> MetricsRunResult:
        ...


class FeatureValidationShapRunnerPort(Protocol):
    def run_shap_review(
        self,
        *,
        scenario_name: str,
        artifact_path: str,
        candidate_feature: str,
        comparison_features: tuple[str, ...],
        validation_mode: str,
        metrics_run_label: str,
        report_run_label: str,
        delta_auc: float,
        delta_logloss: float,
        delta_brier: float,
        run_log_dir: str,
    ) -> ShapReviewResult:
        ...
