from __future__ import annotations

from dataclasses import dataclass, field

from harp.interface.ports import TrackingPort
from harp.interface.ports.validation_runner_ports import MetricsRunResult

from ..theme_tracking import terminate_safely
from .dto import FeatureSelectionDeps, FeatureSelectionRequest
from .reporting import build_scenario_summary
from .scenarios import (
    ScenarioSpec,
    build_scenario_metrics,
    build_scenario_params,
    build_scenario_result,
    build_scenario_tags,
    resolve_scenario_feature_set,
    write_scenario_features_config,
)


@dataclass
class ScenarioExecutionTracker:
    new_scenario_run_ids: dict[str, str] = field(default_factory=dict)
    current_scenario_run_id: str | None = None
    current_scenario_name: str | None = None


def run_selection_scenarios(
    *,
    req: FeatureSelectionRequest,
    deps: FeatureSelectionDeps,
    parent_run_id: str,
    selected_scenarios: tuple[ScenarioSpec, ...],
    base_feature_names: list[str],
    base_cat_features: list[str],
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

        feature_names, cat_features = resolve_scenario_feature_set(
            base_feature_names=base_feature_names,
            base_cat_features=base_cat_features,
            scenario=scenario,
        )
        features_config_path = write_scenario_features_config(
            run_log_dir=run_log_dir,
            file_gateway=deps.file_gateway,
            feature_definition_port=deps.feature_definition_port,
            scenario_name=scenario.scenario_name,
            feature_names=feature_names,
            cat_features=cat_features,
        )
        metrics_run = deps.metrics_runner_port.run_metrics(
            scenario_name=scenario.scenario_name,
            run_log_dir=run_log_dir,
            features_config_path=features_config_path,
        )
        if scenario.scenario_name == "baseline_existing":
            baseline_metrics = metrics_run
        assert baseline_metrics is not None

        result = build_scenario_result(
            scenario=scenario,
            scenario_run_id=tracker.current_scenario_run_id,
            metrics_run=metrics_run,
            baseline_metrics=baseline_metrics,
            enabled_features=tuple(feature_names),
        )

        tracking.log_params(tracker.current_scenario_run_id, build_scenario_params(result))
        tracking.log_metrics(tracker.current_scenario_run_id, build_scenario_metrics(result))
        tracking.log_artifact(tracker.current_scenario_run_id, features_config_path, artifact_path="inputs")
        tracking.log_artifact(tracker.current_scenario_run_id, metrics_run.log_path, artifact_path="logs")
        tracking.log_artifact(tracker.current_scenario_run_id, metrics_run.artifact_path, artifact_path="metrics")
        tracking.log_artifact(tracker.current_scenario_run_id, metrics_run.manifest_path, artifact_path="metrics")
        tracking.log_dict(
            tracker.current_scenario_run_id,
            build_scenario_summary(result, attempt_number=attempt_number),
            artifact_file="summary.json",
        )
        tracking.log_tags(
            tracker.current_scenario_run_id,
            {"attempt_status": "successful", "scenario_attempt": str(attempt_number)},
        )
        tracking.set_terminated(tracker.current_scenario_run_id, status="FINISHED")
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
