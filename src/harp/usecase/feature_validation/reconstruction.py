from __future__ import annotations

from dataclasses import replace

from harp.core.feature_validation_decision import (
    ValidationMetricSnapshot,
    decide_scenario_validation,
)
from harp.interface.ports.validation_runner_ports import MetricsRunResult, ShapReviewResult

from .dto import (
    FeatureValidationRequest,
    ValidationScenarioResult,
)


def result_from_summary(run_id: str, summary: dict[str, object]) -> ValidationScenarioResult:
    scenario_name = str(summary.get("scenario_name", ""))
    metrics_run = metrics_run_from_summary(summary, scenario_name)
    shap_review = shap_review_from_summary(summary, scenario_name)
    return ValidationScenarioResult(
        scenario_run_id=run_id,
        scenario_name=scenario_name,
        enabled_features=tuple(str(item) for item in summary.get("enabled_features", [])),
        enabled_cat_features=tuple(str(item) for item in summary.get("enabled_cat_features", [])),
        features_config_path=str(summary.get("features_config_path", "")),
        metrics_run=metrics_run,
        delta_auc=float(summary.get("delta_auc", 0.0)),
        delta_logloss=float(summary.get("delta_logloss", 0.0)),
        delta_brier=float(summary.get("delta_brier", 0.0)),
        metrics_judgement=str(summary.get("metrics_judgement", "")),
        decision=str(summary.get("decision", "")),
        shap_review=shap_review,
    )


def metrics_run_from_summary(summary: dict[str, object], scenario_name: str) -> MetricsRunResult:
    artifact_path = str(summary.get("artifact_path", ""))
    manifest_path = str(summary.get("manifest_path", ""))
    log_path = str(summary.get("metrics_log_path", ""))
    artifact_paths = tuple(str(path) for path in (artifact_path, manifest_path, log_path) if str(path).strip())
    return MetricsRunResult(
        scenario_name=scenario_name,
        timestamp=str(summary.get("timestamp", "")),
        auc=float(summary.get("auc", 0.0)),
        logloss=float(summary.get("logloss", 0.0)),
        brier=float(summary.get("brier", 0.0)),
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        log_path=log_path,
        artifact_paths=artifact_paths,
    )


def shap_review_from_summary(summary: dict[str, object], scenario_name: str) -> ShapReviewResult | None:
    official_report_path = str(summary.get("official_report_path", ""))
    shap_judgement = str(summary.get("shap_judgement", ""))
    if not official_report_path and not shap_judgement:
        return None
    return ShapReviewResult(
        scenario_name=scenario_name,
        candidate_feature=str(summary.get("candidate_feature", "")),
        metrics_judgement=str(summary.get("shap_metrics_judgement", summary.get("metrics_judgement", ""))),
        shap_judgement=shap_judgement,
        final_recommendation=str(summary.get("final_recommendation", "")),
        official_report_path=official_report_path,
        official_report_source_path=str(summary.get("official_report_source_path", "")),
        summary_json_path=str(summary.get("summary_json_path", "")),
        manifest_json_path=str(summary.get("manifest_json_path", "")),
        artifact_bundle_dir=str(summary.get("artifact_bundle_dir", "")),
        artifact_report_path=str(summary.get("artifact_report_path", "")),
        candidate_dependence_path=str(summary.get("candidate_dependence_path", "")),
        candidate_dependence_source_path=str(summary.get("candidate_dependence_source_path", "")),
        global_rank=str(summary.get("global_rank", "")),
        mean_abs_shap=str(summary.get("mean_abs_shap", "")),
        importance_share=str(summary.get("importance_share", "")),
        log_path=str(summary.get("shap_log_path", "")),
        artifact_paths=tuple(str(path) for path in summary.get("artifact_paths", ())),
    )


def resolve_baseline_metrics(
    existing_results: tuple[ValidationScenarioResult, ...],
    selected_scenarios: tuple,
):
    if selected_scenarios and selected_scenarios[0].scenario_name == "baseline_existing":
        return None
    baseline = next((result for result in existing_results if result.scenario_name == "baseline_existing"), None)
    if baseline is None:
        return None
    return baseline.metrics_run


def normalize_effective_results(
    *,
    req: FeatureValidationRequest,
    result_by_name: dict[str, ValidationScenarioResult],
) -> tuple[ValidationScenarioResult, ...]:
    baseline = result_by_name.get("baseline_existing")
    if baseline is None:
        raise ValueError("baseline_existing is required to reconstruct effective results.")

    ordered_results: list[ValidationScenarioResult] = []
    for scenario in req.scenarios:
        result = result_by_name.get(scenario.scenario_name)
        if result is None:
            continue
        if scenario.scenario_name == "baseline_existing":
            ordered_results.append(
                replace(
                    result,
                    delta_auc=0.0,
                    delta_logloss=0.0,
                    delta_brier=0.0,
                    metrics_judgement="baseline",
                    decision="基準",
                )
            )
            continue

        shap_review = result.shap_review
        decision_result = decide_scenario_validation(
            scenario_name=scenario.scenario_name,
            metrics=_metric_snapshot(result.metrics_run),
            baseline_metrics=_metric_snapshot(baseline.metrics_run),
            shap_judgement=None if shap_review is None else shap_review.shap_judgement,
        )
        if shap_review is not None:
            shap_review = replace(
                shap_review,
                metrics_judgement=decision_result.metrics_judgement,
                final_recommendation=decision_result.final_recommendation,
            )
        ordered_results.append(
            replace(
                result,
                delta_auc=decision_result.delta_auc,
                delta_logloss=decision_result.delta_logloss,
                delta_brier=decision_result.delta_brier,
                metrics_judgement=decision_result.metrics_judgement,
                decision=decision_result.decision,
                shap_review=shap_review,
            )
        )
    return tuple(ordered_results)


def _metric_snapshot(metrics_run: MetricsRunResult) -> ValidationMetricSnapshot:
    return ValidationMetricSnapshot(
        auc=float(metrics_run.auc),
        logloss=float(metrics_run.logloss),
        brier=float(metrics_run.brier),
    )
