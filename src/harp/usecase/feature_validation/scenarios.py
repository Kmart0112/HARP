from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from harp.core.feature_validation_decision import (
    ValidationMetricSnapshot,
    decide_scenario_validation,
    decide_validation_result,
    final_recommendation_for_decision,
)
from harp.interface.ports.validation_runner_ports import ShapReviewResult

from .config_editing import ResolvedScenarioConfig
from .dto import (
    FeatureValidationRequest,
    ValidationScenarioResult,
    ValidationScenarioSpec,
)


def build_scenario_result(
    *,
    scenario: ValidationScenarioSpec,
    scenario_run_id: str,
    resolved_config: ResolvedScenarioConfig,
    scenario_features_config_path: str,
    metrics_run,
    baseline_metrics,
) -> ValidationScenarioResult:
    decision_result = decide_scenario_validation(
        scenario_name=scenario.scenario_name,
        metrics=_metric_snapshot(metrics_run),
        baseline_metrics=_metric_snapshot(baseline_metrics),
    )
    return ValidationScenarioResult(
        scenario_run_id=scenario_run_id,
        scenario_name=scenario.scenario_name,
        enabled_features=resolved_config.feature_names,
        enabled_cat_features=resolved_config.cat_features,
        features_config_path=scenario_features_config_path,
        metrics_run=metrics_run,
        delta_auc=decision_result.delta_auc,
        delta_logloss=decision_result.delta_logloss,
        delta_brier=decision_result.delta_brier,
        metrics_judgement=decision_result.metrics_judgement,
        decision=decision_result.decision,
        shap_review=None,
    )


def apply_shap_review(result: ValidationScenarioResult, shap_review: ShapReviewResult) -> ValidationScenarioResult:
    decision = decide_validation_result(result.metrics_judgement, shap_review.shap_judgement)
    return replace(
        result,
        shap_review=replace(
            shap_review,
            metrics_judgement=result.metrics_judgement,
            final_recommendation=final_recommendation_for_decision(decision),
        ),
        decision=decision,
    )


def build_scenario_tags(
    *,
    req: FeatureValidationRequest,
    scenario: ValidationScenarioSpec,
    attempt_number: int,
) -> dict[str, str]:
    tags = {
        "run_role": "scenario",
        "category": req.category,
        "scenario_name": scenario.scenario_name,
        "scenario_attempt": str(attempt_number),
        "attempt_status": "running",
        "parent_theme_status_at_run": "open",
        "validation_mode": scenario.validation_mode,
        "has_shap": "true" if scenario.shap_request is not None else "false",
    }
    if scenario.shap_request is not None:
        tags["candidate_feature"] = scenario.shap_request.candidate_feature
    return tags


def build_scenario_params(
    *,
    scenario: ValidationScenarioSpec,
    result: ValidationScenarioResult,
) -> dict[str, object]:
    return {
        "scenario_name": scenario.scenario_name,
        "validation_mode": scenario.validation_mode,
        "enabled_features": "|".join(result.enabled_features),
        "enabled_cat_features": "|".join(result.enabled_cat_features),
        "features_config_path": result.features_config_path,
    }


def build_scenario_metrics(result: ValidationScenarioResult) -> dict[str, float]:
    return {
        "auc": result.metrics_run.auc,
        "logloss": result.metrics_run.logloss,
        "brier": result.metrics_run.brier,
        "delta_auc": result.delta_auc,
        "delta_logloss": result.delta_logloss,
        "delta_brier": result.delta_brier,
    }


def _metric_snapshot(metrics_run) -> ValidationMetricSnapshot:  # noqa: ANN001
    return ValidationMetricSnapshot(
        auc=float(metrics_run.auc),
        logloss=float(metrics_run.logloss),
        brier=float(metrics_run.brier),
    )


def materialize_report_images(
    *,
    file_gateway,  # noqa: ANN001
    report_out: str,
    scenario_results: tuple[ValidationScenarioResult, ...],
) -> tuple[ValidationScenarioResult, ...]:
    report_path = Path(report_out)
    images_dir = report_path.parent / "_images"
    report_stem = report_path.stem or "report"
    updated_results: list[ValidationScenarioResult] = []

    for result in scenario_results:
        review = result.shap_review
        if review is None:
            updated_results.append(result)
            continue

        src = review.candidate_dependence_source_path.strip()
        if not src or not Path(src).exists():
            updated_results.append(
                replace(
                    result,
                    shap_review=replace(
                        review,
                        candidate_dependence_path="",
                        candidate_dependence_source_path="",
                    ),
                )
            )
            continue

        suffix = Path(src).suffix or ".png"
        dst = images_dir / f"{report_stem}_{review.candidate_feature}_dependence{suffix}"
        file_gateway.copy(src, str(dst))
        updated_results.append(
            replace(
                result,
                shap_review=replace(
                    review,
                    candidate_dependence_path=str(dst),
                    candidate_dependence_source_path=str(dst),
                ),
            )
        )
    return tuple(updated_results)
