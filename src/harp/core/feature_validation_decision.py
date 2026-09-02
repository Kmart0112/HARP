from __future__ import annotations

from dataclasses import dataclass


BASELINE_SCENARIO_NAME = "baseline_existing"


@dataclass(frozen=True)
class ValidationMetricSnapshot:
    auc: float
    logloss: float
    brier: float


@dataclass(frozen=True)
class ValidationDecisionResult:
    delta_auc: float
    delta_logloss: float
    delta_brier: float
    metrics_judgement: str
    decision: str
    final_recommendation: str


def decide_scenario_validation(
    *,
    scenario_name: str,
    metrics: ValidationMetricSnapshot,
    baseline_metrics: ValidationMetricSnapshot,
    shap_judgement: str | None = None,
) -> ValidationDecisionResult:
    if scenario_name == BASELINE_SCENARIO_NAME:
        return ValidationDecisionResult(
            delta_auc=0.0,
            delta_logloss=0.0,
            delta_brier=0.0,
            metrics_judgement="baseline",
            decision="基準",
            final_recommendation="",
        )

    delta_auc = float(metrics.auc) - float(baseline_metrics.auc)
    delta_logloss = float(metrics.logloss) - float(baseline_metrics.logloss)
    delta_brier = float(metrics.brier) - float(baseline_metrics.brier)
    metrics_judgement = judge_metrics(delta_auc, delta_logloss)
    if shap_judgement is None:
        decision = decide_metrics_only(delta_auc, delta_logloss)
    else:
        decision = decide_validation_result(metrics_judgement, shap_judgement)
    return ValidationDecisionResult(
        delta_auc=delta_auc,
        delta_logloss=delta_logloss,
        delta_brier=delta_brier,
        metrics_judgement=metrics_judgement,
        decision=decision,
        final_recommendation=final_recommendation_for_decision(decision),
    )


def judge_metrics(delta_auc: float, delta_logloss: float) -> str:
    if delta_auc > 0 and delta_logloss < 0:
        return "improved"
    if delta_auc > 0 or delta_logloss < 0:
        return "mixed"
    return "not_improved"


def decide_metrics_only(delta_auc: float, delta_logloss: float) -> str:
    if delta_auc > 0 and delta_logloss < 0:
        return "採用"
    if delta_auc > 0 or delta_logloss < 0:
        return "保留"
    return "不採用"


def decide_validation_result(metrics_judgement: str, shap_judgement: str) -> str:
    if metrics_judgement == "improved":
        if shap_judgement == "問題なし":
            return "採用"
        return "保留"
    if metrics_judgement == "mixed":
        return "保留"
    return "不採用"


def final_recommendation_for_decision(decision: str) -> str:
    if decision == "採用":
        return "adopt"
    if decision == "保留":
        return "hold"
    return "reject"


def decide_overall_validation_result(
    decisions: tuple[str, ...],
    *,
    final_selected_decision: str | None = None,
) -> str:
    if final_selected_decision is not None:
        return final_selected_decision
    non_baseline_decisions = {decision for decision in decisions if decision != "基準"}
    if "採用" in non_baseline_decisions:
        return "採用"
    if "保留" in non_baseline_decisions:
        return "保留"
    return "不採用"
