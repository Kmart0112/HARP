from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harp.interface.ports import FeatureDefinitionPort, FileGatewayPort

from ..theme_tracking import safe_token
from .dto import FeatureSelectionRequest, FeatureSelectionScenarioResult


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_name: str
    phase: str
    group_id: str | None
    tested_set: str
    include_features: tuple[str, ...]
    exclude_features: tuple[str, ...]


def build_scenarios(req: FeatureSelectionRequest) -> tuple[ScenarioSpec, ...]:
    scenarios: list[ScenarioSpec] = [
        ScenarioSpec(
            scenario_name="baseline_existing",
            phase="baseline",
            group_id=None,
            tested_set="baseline",
            include_features=(),
            exclude_features=(),
        )
    ]
    for group in req.aggregate_groups:
        scenarios.extend(
            [
                ScenarioSpec(
                    scenario_name=f"aggregate__{group.group_id}__aggregate_only",
                    phase="aggregate",
                    group_id=group.group_id,
                    tested_set="aggregate_only",
                    include_features=tuple(group.aggregate_features),
                    exclude_features=tuple(group.source_features),
                ),
                ScenarioSpec(
                    scenario_name=f"aggregate__{group.group_id}__source_only",
                    phase="aggregate",
                    group_id=group.group_id,
                    tested_set="source_only",
                    include_features=tuple(group.source_features),
                    exclude_features=tuple(group.aggregate_features),
                ),
                ScenarioSpec(
                    scenario_name=f"aggregate__{group.group_id}__all_features",
                    phase="aggregate",
                    group_id=group.group_id,
                    tested_set="all_features",
                    include_features=tuple((*group.aggregate_features, *group.source_features)),
                    exclude_features=(),
                ),
            ]
        )
    for group in req.variant_groups:
        for candidate in group.candidates:
            scenarios.append(
                ScenarioSpec(
                    scenario_name=f"variant__{group.group_id}__{candidate}",
                    phase="variant",
                    group_id=group.group_id,
                    tested_set=candidate,
                    include_features=(candidate,),
                    exclude_features=tuple(other for other in group.candidates if other != candidate),
                )
            )
    return tuple(scenarios)


def resolve_scenario_feature_set(
    *,
    base_feature_names: list[str],
    base_cat_features: list[str],
    scenario: ScenarioSpec,
) -> tuple[list[str], list[str]]:
    feature_names = merge_feature_list(base_feature_names, scenario.include_features, scenario.exclude_features)
    cat_features = [feature for feature in base_cat_features if feature in set(feature_names)]
    return feature_names, cat_features


def merge_feature_list(base: list[str], includes: tuple[str, ...], excludes: tuple[str, ...]) -> list[str]:
    excluded = set(excludes)
    merged = [feature for feature in base if feature not in excluded]
    seen = set(merged)
    for feature in includes:
        if feature in seen:
            continue
        merged.append(feature)
        seen.add(feature)
    return merged


def write_scenario_features_config(
    *,
    run_log_dir: str,
    file_gateway: FileGatewayPort,
    feature_definition_port: FeatureDefinitionPort,
    scenario_name: str,
    feature_names: list[str],
    cat_features: list[str],
) -> str:
    scenario_path = str(Path(run_log_dir) / "inputs" / f"features_{safe_token(scenario_name)}.yml")
    file_gateway.write_text(
        scenario_path,
        feature_definition_port.render_feature_config(
            feature_names=feature_names,
            cat_features=cat_features,
        ),
    )
    return scenario_path


def build_scenario_result(
    *,
    scenario: ScenarioSpec,
    scenario_run_id: str,
    metrics_run,
    baseline_metrics,
    enabled_features: tuple[str, ...],
) -> FeatureSelectionScenarioResult:
    delta_auc = float(metrics_run.auc) - float(baseline_metrics.auc)
    delta_logloss = float(metrics_run.logloss) - float(baseline_metrics.logloss)
    delta_brier = float(metrics_run.brier) - float(baseline_metrics.brier)
    metrics_judgement = "baseline" if scenario.phase == "baseline" else judge_metrics(delta_auc, delta_logloss)
    return FeatureSelectionScenarioResult(
        scenario_run_id=scenario_run_id,
        scenario_name=scenario.scenario_name,
        phase=scenario.phase,
        group_id=scenario.group_id,
        tested_set=scenario.tested_set,
        enabled_features=enabled_features,
        metrics_run=metrics_run,
        delta_auc=delta_auc,
        delta_logloss=delta_logloss,
        delta_brier=delta_brier,
        metrics_judgement=metrics_judgement,
    )


def judge_metrics(delta_auc: float, delta_logloss: float) -> str:
    if delta_auc > 0 and delta_logloss < 0:
        return "improved"
    if delta_auc > 0 or delta_logloss < 0:
        return "mixed"
    return "not_improved"


def build_scenario_tags(
    *,
    req: FeatureSelectionRequest,
    scenario: ScenarioSpec,
    attempt_number: int,
) -> dict[str, str]:
    tags = {
        "run_role": "scenario",
        "category": req.category,
        "scenario_name": scenario.scenario_name,
        "scenario_attempt": str(attempt_number),
        "attempt_status": "running",
        "parent_theme_status_at_run": "open",
        "phase": scenario.phase,
        "tested_set": scenario.tested_set,
    }
    if scenario.group_id is not None:
        tags["group_id"] = scenario.group_id
    return tags


def build_scenario_params(result: FeatureSelectionScenarioResult) -> dict[str, object]:
    return {
        "scenario_name": result.scenario_name,
        "phase": result.phase,
        "group_id": "" if result.group_id is None else result.group_id,
        "tested_set": result.tested_set,
        "enabled_features": "|".join(result.enabled_features),
    }

def build_scenario_metrics(result: FeatureSelectionScenarioResult) -> dict[str, float]:
    return {
        "auc": result.metrics_run.auc,
        "logloss": result.metrics_run.logloss,
        "brier": result.metrics_run.brier,
        "delta_auc": result.delta_auc,
        "delta_logloss": result.delta_logloss,
        "delta_brier": result.delta_brier,
    }
