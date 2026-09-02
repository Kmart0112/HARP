from __future__ import annotations

from dataclasses import dataclass

from .feature_validation_decision import decide_overall_validation_result


@dataclass(frozen=True)
class FeatureValidationReportScenarioSpec:
    scenario_name: str
    validation_mode: str
    candidate_feature: str = ""
    enabled_toggle_features: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureValidationReportScenarioResult:
    scenario_name: str
    enabled_features: tuple[str, ...]
    decision: str


@dataclass(frozen=True)
class FeatureValidationFeatureVerdict:
    feature_name: str
    verdict: str


@dataclass(frozen=True)
class FeatureValidationReportModel:
    decision: str
    final_selected_scenario: str
    final_selected_features: tuple[str, ...]
    feature_verdicts: tuple[FeatureValidationFeatureVerdict, ...]
    adopted_features: tuple[str, ...]
    held_features: tuple[str, ...]
    rejected_features: tuple[str, ...]

    @property
    def feature_verdict_by_name(self) -> dict[str, str]:
        return {item.feature_name: item.verdict for item in self.feature_verdicts}


def build_feature_validation_report_model(
    *,
    target_features: tuple[str, ...],
    scenarios: tuple[FeatureValidationReportScenarioSpec, ...],
    scenario_results: tuple[FeatureValidationReportScenarioResult, ...],
    baseline_scenario_name: str,
    finalize: bool,
    final_selected_scenario: str | None,
) -> FeatureValidationReportModel:
    result_by_name = {result.scenario_name: result for result in scenario_results}
    baseline = result_by_name[baseline_scenario_name]
    final_selected_result = _resolve_final_selected_result(
        scenario_results=scenario_results,
        finalize=finalize,
        final_selected_scenario=final_selected_scenario,
    )
    final_selected_features = _resolve_selected_features(
        target_features=target_features,
        baseline=baseline,
        final_selected_result=final_selected_result,
    )
    feature_verdicts = _build_feature_verdicts(
        target_features=target_features,
        scenarios=scenarios,
        result_by_name=result_by_name,
        final_selected_result=final_selected_result,
        final_selected_features=final_selected_features,
    )
    verdict_by_feature = {item.feature_name: item.verdict for item in feature_verdicts}
    decision = decide_overall_validation_result(
        tuple(result.decision for result in scenario_results),
        final_selected_decision=None if final_selected_result is None else final_selected_result.decision,
    )
    return FeatureValidationReportModel(
        decision=decision,
        final_selected_scenario="" if final_selected_result is None else final_selected_result.scenario_name,
        final_selected_features=final_selected_features,
        feature_verdicts=feature_verdicts,
        adopted_features=tuple(feature for feature in target_features if verdict_by_feature[feature] == "採用"),
        held_features=tuple(feature for feature in target_features if verdict_by_feature[feature] == "保留"),
        rejected_features=tuple(feature for feature in target_features if verdict_by_feature[feature] == "不採用"),
    )


def _resolve_final_selected_result(
    *,
    scenario_results: tuple[FeatureValidationReportScenarioResult, ...],
    finalize: bool,
    final_selected_scenario: str | None,
) -> FeatureValidationReportScenarioResult | None:
    if not finalize or not final_selected_scenario:
        return None
    result = next((item for item in scenario_results if item.scenario_name == final_selected_scenario), None)
    if result is None:
        raise ValueError(f"final_selected_scenario not found in effective results: {final_selected_scenario}")
    return result


def _resolve_selected_features(
    *,
    target_features: tuple[str, ...],
    baseline: FeatureValidationReportScenarioResult,
    final_selected_result: FeatureValidationReportScenarioResult | None,
) -> tuple[str, ...]:
    if final_selected_result is None:
        return ()
    baseline_features = set(baseline.enabled_features)
    return tuple(
        feature
        for feature in target_features
        if feature in final_selected_result.enabled_features and feature not in baseline_features
    )


def _build_feature_verdicts(
    *,
    target_features: tuple[str, ...],
    scenarios: tuple[FeatureValidationReportScenarioSpec, ...],
    result_by_name: dict[str, FeatureValidationReportScenarioResult],
    final_selected_result: FeatureValidationReportScenarioResult | None,
    final_selected_features: tuple[str, ...],
) -> tuple[FeatureValidationFeatureVerdict, ...]:
    if final_selected_result is not None:
        selected = set(final_selected_features)
        chosen_verdict = final_selected_result.decision if final_selected_result.decision != "基準" else "不採用"
        return tuple(
            FeatureValidationFeatureVerdict(
                feature_name=feature,
                verdict=chosen_verdict if feature in selected else "不採用",
            )
            for feature in target_features
        )

    verdicts: list[FeatureValidationFeatureVerdict] = []
    for feature in target_features:
        canonical_result = _find_canonical_feature_result(
            feature_name=feature,
            scenarios=scenarios,
            result_by_name=result_by_name,
        )
        verdicts.append(
            FeatureValidationFeatureVerdict(
                feature_name=feature,
                verdict=canonical_result.decision if canonical_result is not None else "未評価",
            )
        )
    return tuple(verdicts)


def _find_canonical_feature_result(
    *,
    feature_name: str,
    scenarios: tuple[FeatureValidationReportScenarioSpec, ...],
    result_by_name: dict[str, FeatureValidationReportScenarioResult],
) -> FeatureValidationReportScenarioResult | None:
    for scenario in scenarios:
        if scenario.candidate_feature != feature_name:
            continue
        result = result_by_name.get(scenario.scenario_name)
        if result is not None:
            return result

    for scenario in scenarios:
        enabled_features = tuple(sorted(scenario.enabled_toggle_features))
        if enabled_features != (feature_name,):
            continue
        result = result_by_name.get(scenario.scenario_name)
        if result is not None:
            return result

    for scenario in scenarios:
        if scenario.validation_mode != "single_add":
            continue
        if feature_name not in scenario.enabled_toggle_features:
            continue
        result = result_by_name.get(scenario.scenario_name)
        if result is not None:
            return result

    return None
