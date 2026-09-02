from __future__ import annotations

from dataclasses import dataclass, field

from harp.interface.ports import TrackingPort
from harp.interface.ports.validation_runner_ports import MetricsRunResult
from harp.shared.logging import get_logger

from ..theme_tracking import terminate_safely
from .config_editing import resolve_scenario_config, write_scenario_features_config
from .dto import FeatureValidationDeps, FeatureValidationRequest, ValidationScenarioSpec
from .reporting import build_shap_summary
from .scenarios import (
    apply_shap_review,
    build_scenario_metrics,
    build_scenario_params,
    build_scenario_result,
    build_scenario_tags,
)

logger = get_logger(__name__)


@dataclass
class ScenarioExecutionTracker:
    new_scenario_run_ids: dict[str, str] = field(default_factory=dict)
    current_scenario_run_id: str | None = None
    current_scenario_name: str | None = None


def run_validation_scenarios(
    *,
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
    parent_run_id: str,
    selected_scenarios: tuple[ValidationScenarioSpec, ...],
    original_text: str,
    run_log_dir: str,
    initial_baseline_metrics: MetricsRunResult | None,
    attempt_counts: dict[str, int],
    tracker: ScenarioExecutionTracker,
) -> None:
    tracking = deps.tracking_port
    baseline_metrics = initial_baseline_metrics

    for scenario in selected_scenarios:
        attempt_number = attempt_counts.get(scenario.scenario_name, 0) + 1
        attempt_counts[scenario.scenario_name] = attempt_number
        tracker.current_scenario_name = scenario.scenario_name
        tracker.current_scenario_run_id = tracking.start_run(
            experiment_name=req.experiment_name,
            run_name=scenario.scenario_name,
            tags=build_scenario_tags(req=req, scenario=scenario, attempt_number=attempt_number),
            parent_run_id=parent_run_id,
        )
        tracker.new_scenario_run_ids[scenario.scenario_name] = tracker.current_scenario_run_id
        logger.info(
            "feature validation scenario started scenario=%s attempt=%s run_id=%s parent_run_id=%s mode=%s",
            scenario.scenario_name,
            attempt_number,
            tracker.current_scenario_run_id,
            parent_run_id,
            scenario.validation_mode,
        )

        resolved_config = resolve_scenario_config(
            original_text=original_text,
            scenario=scenario,
            feature_definition_port=deps.feature_definition_port,
            feature_sets_path=req.feature_sets_path,
        )
        scenario_features_config_path = write_scenario_features_config(
            run_log_dir=run_log_dir,
            file_gateway=deps.file_gateway,
            scenario_name=scenario.scenario_name,
            scenario_text=resolved_config.scenario_text,
        )
        metrics_run = deps.metrics_runner_port.run_metrics(
            scenario_name=scenario.scenario_name,
            run_log_dir=run_log_dir,
            features_config_path=scenario_features_config_path,
        )
        if scenario.scenario_name == "baseline_existing":
            baseline_metrics = metrics_run
        assert baseline_metrics is not None

        result = build_scenario_result(
            scenario=scenario,
            scenario_run_id=tracker.current_scenario_run_id,
            resolved_config=resolved_config,
            scenario_features_config_path=scenario_features_config_path,
            metrics_run=metrics_run,
            baseline_metrics=baseline_metrics,
        )

        tracking.log_params(tracker.current_scenario_run_id, build_scenario_params(scenario=scenario, result=result))
        tracking.log_metrics(tracker.current_scenario_run_id, build_scenario_metrics(result))
        tracking.log_artifact(tracker.current_scenario_run_id, scenario_features_config_path, artifact_path="inputs")
        tracking.log_artifact(tracker.current_scenario_run_id, metrics_run.log_path, artifact_path="logs")
        tracking.log_artifact(tracker.current_scenario_run_id, metrics_run.artifact_path, artifact_path="metrics")
        tracking.log_artifact(tracker.current_scenario_run_id, metrics_run.manifest_path, artifact_path="metrics")

        if scenario.shap_request is not None:
            shap_request = scenario.shap_request
            shap_review = deps.shap_runner_port.run_shap_review(
                scenario_name=scenario.scenario_name,
                artifact_path=result.metrics_run.artifact_path,
                candidate_feature=shap_request.candidate_feature,
                comparison_features=shap_request.comparison_features,
                validation_mode=scenario.validation_mode,
                metrics_run_label=scenario.scenario_name,
                report_run_label=shap_request.report_run_label,
                delta_auc=result.delta_auc,
                delta_logloss=result.delta_logloss,
                delta_brier=result.delta_brier,
                run_log_dir=run_log_dir,
            )
            result = apply_shap_review(result, shap_review)
            tracking.log_tags(
                tracker.current_scenario_run_id,
                {
                    "candidate_feature": shap_request.candidate_feature,
                    "comparison_features": "|".join(shap_request.comparison_features),
                },
            )
            tracking.log_artifact(tracker.current_scenario_run_id, shap_review.log_path, artifact_path="logs")
            tracking.log_artifacts(
                tracker.current_scenario_run_id,
                shap_review.artifact_bundle_dir,
                artifact_path="shap/bundle",
            )
            tracking.log_artifact(
                tracker.current_scenario_run_id,
                shap_review.official_report_source_path,
                artifact_path="shap",
            )

        tracking.log_dict(
            tracker.current_scenario_run_id,
            build_shap_summary(result, attempt_number=attempt_number),
            artifact_file="summary.json",
        )
        tracking.log_tags(
            tracker.current_scenario_run_id,
            {
                "attempt_status": "successful",
                "scenario_attempt": str(attempt_number),
            },
        )
        tracking.set_terminated(tracker.current_scenario_run_id, status="FINISHED")
        logger.info(
            "feature validation scenario finished scenario=%s attempt=%s run_id=%s auc=%.9f logloss=%.9f brier=%.9f delta_auc=%.9f delta_logloss=%.9f delta_brier=%.9f shap_judgement=%s",
            scenario.scenario_name,
            attempt_number,
            tracker.current_scenario_run_id,
            result.metrics_run.auc,
            result.metrics_run.logloss,
            result.metrics_run.brier,
            result.delta_auc,
            result.delta_logloss,
            result.delta_brier,
            result.shap_review.shap_judgement if result.shap_review is not None else "-",
        )
        tracker.current_scenario_run_id = None
        tracker.current_scenario_name = None


def mark_started_scenario_runs_failed(
    *,
    tracking: TrackingPort,
    tracker: ScenarioExecutionTracker,
) -> None:
    if tracker.current_scenario_run_id is not None:
        try:
            tracking.log_tags(tracker.current_scenario_run_id, {"attempt_status": "failed"})
        except Exception:
            pass
    for run_id in dict.fromkeys([*tracker.new_scenario_run_ids.values(), tracker.current_scenario_run_id]):
        terminate_safely(tracking, run_id, "FAILED")
