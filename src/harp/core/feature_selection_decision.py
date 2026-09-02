from __future__ import annotations

from dataclasses import dataclass


_SIMPLE_ORDER = {
    "aggregate_only": 0,
    "source_only": 1,
    "all_features": 2,
}


@dataclass(frozen=True)
class SelectionCandidateMetrics:
    tested_set: str
    delta_auc: float
    delta_logloss: float
    delta_brier: float

    def score_tuple(self) -> tuple[float, float, float]:
        return (self.delta_auc, -self.delta_logloss, -self.delta_brier)


@dataclass(frozen=True)
class SelectionDecision:
    group_id: str
    decision_type: str
    winner_set: str
    loser_sets: tuple[str, ...]
    reason: str
    delta_auc: float | None
    delta_logloss: float | None
    delta_brier: float | None
    unresolved: bool = False


def is_improved(candidate: SelectionCandidateMetrics, *, auc_threshold: float, logloss_threshold: float) -> bool:
    return candidate.delta_auc > auc_threshold and candidate.delta_logloss < logloss_threshold


def choose_aggregate_decision(
    *,
    group_id: str,
    candidates: dict[str, SelectionCandidateMetrics],
    auc_threshold: float,
    logloss_threshold: float,
) -> SelectionDecision:
    required = ("aggregate_only", "source_only", "all_features")
    missing = [name for name in required if name not in candidates]
    if missing:
        return SelectionDecision(
            group_id=group_id,
            decision_type="aggregate",
            winner_set="",
            loser_sets=(),
            reason=f"unresolved_missing::{','.join(missing)}",
            delta_auc=None,
            delta_logloss=None,
            delta_brier=None,
            unresolved=True,
        )

    rows = [candidates[name] for name in required]
    improved = [row for row in rows if is_improved(row, auc_threshold=auc_threshold, logloss_threshold=logloss_threshold)]
    contenders = improved or rows
    best = max(contenders, key=lambda row: row.score_tuple())
    near_tied = [
        row
        for row in contenders
        if _is_near_tie(best, row, auc_threshold=auc_threshold, logloss_threshold=logloss_threshold)
    ]
    if len(near_tied) > 1:
        best = min(near_tied, key=lambda row: _SIMPLE_ORDER[row.tested_set])
        reason = "tie_prefer_simpler" if improved else "relative_tie_prefer_simpler"
    else:
        reason = "improved_best" if improved else "relative_best"

    return SelectionDecision(
        group_id=group_id,
        decision_type="aggregate",
        winner_set=best.tested_set,
        loser_sets=tuple(name for name in required if name != best.tested_set),
        reason=reason,
        delta_auc=best.delta_auc,
        delta_logloss=best.delta_logloss,
        delta_brier=best.delta_brier,
        unresolved=False,
    )


def choose_variant_decision(
    *,
    group_id: str,
    candidates: tuple[str, ...],
    results: dict[str, SelectionCandidateMetrics],
    current_enabled_candidates: tuple[str, ...],
    auc_threshold: float,
    logloss_threshold: float,
) -> SelectionDecision:
    missing = [candidate for candidate in candidates if candidate not in results]
    if missing:
        return SelectionDecision(
            group_id=group_id,
            decision_type="variant",
            winner_set="",
            loser_sets=(),
            reason=f"unresolved_missing::{','.join(missing)}",
            delta_auc=None,
            delta_logloss=None,
            delta_brier=None,
            unresolved=True,
        )

    rows = [results[candidate] for candidate in candidates]
    improved = [row for row in rows if is_improved(row, auc_threshold=auc_threshold, logloss_threshold=logloss_threshold)]
    if improved:
        best = max(improved, key=lambda row: row.score_tuple())
        return SelectionDecision(
            group_id=group_id,
            decision_type="variant",
            winner_set=best.tested_set,
            loser_sets=tuple(candidate for candidate in candidates if candidate != best.tested_set),
            reason="improved_best",
            delta_auc=best.delta_auc,
            delta_logloss=best.delta_logloss,
            delta_brier=best.delta_brier,
            unresolved=False,
        )

    if len(current_enabled_candidates) == 1:
        winner = current_enabled_candidates[0]
        best = results[winner]
        return SelectionDecision(
            group_id=group_id,
            decision_type="variant",
            winner_set=winner,
            loser_sets=tuple(candidate for candidate in candidates if candidate != winner),
            reason="current_keep",
            delta_auc=best.delta_auc,
            delta_logloss=best.delta_logloss,
            delta_brier=best.delta_brier,
            unresolved=False,
        )

    suffix = "none" if len(current_enabled_candidates) == 0 else "multiple"
    return SelectionDecision(
        group_id=group_id,
        decision_type="variant",
        winner_set="",
        loser_sets=(),
        reason=f"unresolved_current_keep::{suffix}",
        delta_auc=None,
        delta_logloss=None,
        delta_brier=None,
        unresolved=True,
    )


def _is_near_tie(
    left: SelectionCandidateMetrics,
    right: SelectionCandidateMetrics,
    *,
    auc_threshold: float,
    logloss_threshold: float,
) -> bool:
    logloss_eps = abs(logloss_threshold)
    return (
        abs(left.delta_auc - right.delta_auc) <= auc_threshold
        and abs(left.delta_logloss - right.delta_logloss) <= logloss_eps
    )
