from __future__ import annotations

from harp.interface.ports.validation_runner_ports import MetricsRunResult

from .scenarios import ScenarioSpec, judge_metrics
from .dto import FeatureSelectionScenarioResult


def resolve_baseline_metrics(
    existing_results: tuple[FeatureSelectionScenarioResult, ...],
    selected_scenarios: tuple[ScenarioSpec, ...],
) -> MetricsRunResult | None:
    if selected_scenarios and selected_scenarios[0].scenario_name == "baseline_existing":
        return None
    baseline = next((result for result in existing_results if result.scenario_name == "baseline_existing"), None)
    if baseline is None:
        return None
    return baseline.metrics_run


def scenario_result_from_summary(run_id: str, summary: dict[str, object]) -> FeatureSelectionScenarioResult:
    return FeatureSelectionScenarioResult(
        scenario_run_id=run_id,
        scenario_name=str(summary.get("scenario_name", "")),
        phase=str(summary.get("phase", "")),
        group_id=(None if summary.get("group_id") in (None, "") else str(summary.get("group_id"))),
        tested_set=str(summary.get("tested_set", "")),
        enabled_features=tuple(str(item) for item in summary.get("enabled_features", [])),
        metrics_run=MetricsRunResult(
            scenario_name=str(summary.get("scenario_name", "")),
            timestamp=str(summary.get("timestamp", "")),
            auc=float(summary.get("auc", 0.0)),
            logloss=float(summary.get("logloss", 0.0)),
            brier=float(summary.get("brier", 0.0)),
            artifact_path=str(summary.get("artifact_path", "")),
            manifest_path=str(summary.get("manifest_path", "")),
            log_path=str(summary.get("metrics_log_path", "")),
            artifact_paths=tuple(str(path) for path in summary.get("artifact_paths", ())),
        ),
        delta_auc=float(summary.get("delta_auc", 0.0)),
        delta_logloss=float(summary.get("delta_logloss", 0.0)),
        delta_brier=float(summary.get("delta_brier", 0.0)),
        metrics_judgement=str(summary.get("metrics_judgement", "")),
    )


def normalize_effective_results(
    *,
    scenarios: tuple[ScenarioSpec, ...],
    result_by_name: dict[str, FeatureSelectionScenarioResult],
) -> tuple[FeatureSelectionScenarioResult, ...]:
    baseline = result_by_name.get("baseline_existing")
    if baseline is None:
        raise ValueError("baseline_existing is required to reconstruct effective results.")

    ordered_results: list[FeatureSelectionScenarioResult] = []
    for scenario in scenarios:
        result = result_by_name.get(scenario.scenario_name)
        if result is None:
            continue
        if scenario.scenario_name == "baseline_existing":
            ordered_results.append(
                FeatureSelectionScenarioResult(
                    scenario_run_id=result.scenario_run_id,
                    scenario_name=result.scenario_name,
                    phase=result.phase,
                    group_id=result.group_id,
                    tested_set=result.tested_set,
                    enabled_features=result.enabled_features,
                    metrics_run=result.metrics_run,
                    delta_auc=0.0,
                    delta_logloss=0.0,
                    delta_brier=0.0,
                    metrics_judgement="baseline",
                )
            )
            continue
        delta_auc = float(result.metrics_run.auc) - float(baseline.metrics_run.auc)
        delta_logloss = float(result.metrics_run.logloss) - float(baseline.metrics_run.logloss)
        delta_brier = float(result.metrics_run.brier) - float(baseline.metrics_run.brier)
        ordered_results.append(
            FeatureSelectionScenarioResult(
                scenario_run_id=result.scenario_run_id,
                scenario_name=result.scenario_name,
                phase=result.phase,
                group_id=result.group_id,
                tested_set=result.tested_set,
                enabled_features=result.enabled_features,
                metrics_run=result.metrics_run,
                delta_auc=delta_auc,
                delta_logloss=delta_logloss,
                delta_brier=delta_brier,
                metrics_judgement=judge_metrics(delta_auc, delta_logloss),
            )
        )
    return tuple(ordered_results)
