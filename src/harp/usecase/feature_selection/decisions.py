from __future__ import annotations

from harp.core.feature_selection_decision import (
    SelectionCandidateMetrics,
    choose_aggregate_decision,
    choose_variant_decision,
)

from .scenarios import merge_feature_list
from .dto import (
    AggregateGroupSpec,
    FeatureSelectionDecisionRow,
    FeatureSelectionRequest,
    FeatureSelectionScenarioResult,
    VariantGroupSpec,
)


def build_decisions(
    *,
    req: FeatureSelectionRequest,
    scenario_results: tuple[FeatureSelectionScenarioResult, ...],
    base_feature_names: list[str],
    base_cat_features: list[str],
    auc_threshold: float,
    logloss_threshold: float,
) -> tuple[tuple[FeatureSelectionDecisionRow, ...], list[str], list[str]]:
    results_by_group: dict[str, dict[str, FeatureSelectionScenarioResult]] = {}
    for result in scenario_results:
        if result.group_id is None:
            continue
        results_by_group.setdefault(result.group_id, {})[result.tested_set] = result

    decisions: list[FeatureSelectionDecisionRow] = []
    current_feature_names = list(base_feature_names)
    current_cat_features = list(base_cat_features)

    for group in req.aggregate_groups:
        decision = choose_aggregate_decision(
            group_id=group.group_id,
            candidates={
                tested_set: SelectionCandidateMetrics(
                    tested_set=tested_set,
                    delta_auc=result.delta_auc,
                    delta_logloss=result.delta_logloss,
                    delta_brier=result.delta_brier,
                )
                for tested_set, result in results_by_group.get(group.group_id, {}).items()
            },
            auc_threshold=auc_threshold,
            logloss_threshold=logloss_threshold,
        )
        row = decision_row_from_core(decision)
        decisions.append(row)
        current_feature_names, current_cat_features = apply_aggregate_decision(
            feature_names=current_feature_names,
            cat_features=current_cat_features,
            group=group,
            decision=row,
            base_cat_features=base_cat_features,
        )

    for group in req.variant_groups:
        current_enabled_candidates = tuple(candidate for candidate in group.candidates if candidate in current_feature_names)
        decision = choose_variant_decision(
            group_id=group.group_id,
            candidates=tuple(group.candidates),
            results={
                tested_set: SelectionCandidateMetrics(
                    tested_set=tested_set,
                    delta_auc=result.delta_auc,
                    delta_logloss=result.delta_logloss,
                    delta_brier=result.delta_brier,
                )
                for tested_set, result in results_by_group.get(group.group_id, {}).items()
            },
            current_enabled_candidates=current_enabled_candidates,
            auc_threshold=auc_threshold,
            logloss_threshold=logloss_threshold,
        )
        row = decision_row_from_core(decision)
        decisions.append(row)
        current_feature_names, current_cat_features = apply_variant_decision(
            feature_names=current_feature_names,
            cat_features=current_cat_features,
            group=group,
            decision=row,
            base_cat_features=base_cat_features,
        )

    return tuple(decisions), current_feature_names, current_cat_features


def decision_row_from_core(decision) -> FeatureSelectionDecisionRow:  # noqa: ANN001
    return FeatureSelectionDecisionRow(
        group_id=decision.group_id,
        decision_type=decision.decision_type,
        winner_set=decision.winner_set,
        loser_sets=tuple(decision.loser_sets),
        reason=decision.reason,
        delta_auc=decision.delta_auc,
        delta_logloss=decision.delta_logloss,
        delta_brier=decision.delta_brier,
        unresolved=bool(decision.unresolved),
    )


def apply_aggregate_decision(
    *,
    feature_names: list[str],
    cat_features: list[str],
    group: AggregateGroupSpec,
    decision: FeatureSelectionDecisionRow,
    base_cat_features: list[str],
) -> tuple[list[str], list[str]]:
    if decision.unresolved:
        return feature_names, cat_features
    if decision.winner_set == "aggregate_only":
        next_feature_names = merge_feature_list(feature_names, tuple(group.aggregate_features), tuple(group.source_features))
    elif decision.winner_set == "source_only":
        next_feature_names = merge_feature_list(feature_names, tuple(group.source_features), tuple(group.aggregate_features))
    else:
        next_feature_names = merge_feature_list(
            feature_names,
            tuple((*group.aggregate_features, *group.source_features)),
            (),
        )
    next_cat_features = [feature for feature in base_cat_features if feature in set(next_feature_names)]
    return next_feature_names, next_cat_features


def apply_variant_decision(
    *,
    feature_names: list[str],
    cat_features: list[str],
    group: VariantGroupSpec,
    decision: FeatureSelectionDecisionRow,
    base_cat_features: list[str],
) -> tuple[list[str], list[str]]:
    if decision.unresolved or not decision.winner_set:
        return feature_names, cat_features
    next_feature_names = merge_feature_list(feature_names, (decision.winner_set,), tuple(group.candidates))
    next_cat_features = [feature for feature in base_cat_features if feature in set(next_feature_names)]
    return next_feature_names, next_cat_features
