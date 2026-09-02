from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.special import expit

from .empirical_bayes import EmpiricalBayesFitResult, fit_empirical_bayes_interactions
from .regularized_logistic import (
    InteractionLogisticModel,
    binary_brier_score,
    binary_log_loss,
    fit_regularized_interaction_logistic,
)
from .specs import (
    ConditionSpec,
    ConfirmationPolicy,
    EntitySpec,
    ObservationSchema,
    ScreeningPolicy,
)
from .time_validation import (
    BootstrapInterval,
    block_bootstrap_mean,
    build_expanding_window_folds,
    build_inner_tuning_split,
)
from .transforms import materialize_condition


Decision = Literal["confirmed", "rejected", "inconclusive"]


@dataclass(frozen=True)
class PairScreenResult:
    summary: dict[str, object]
    cell_effects: pd.DataFrame
    fit: EmpiricalBayesFitResult


@dataclass(frozen=True)
class PairConfirmationResult:
    summary: dict[str, object]
    fold_metrics: pd.DataFrame
    oos_predictions: pd.DataFrame
    cell_stability: pd.DataFrame


def prepare_pair_frame(
    frame: pd.DataFrame,
    *,
    entity: EntitySpec,
    condition: ConditionSpec,
    schema: ObservationSchema,
) -> pd.DataFrame:
    entity.validate()
    condition.validate()
    schema.validate()
    required = {
        *schema.key_cols,
        schema.race_id_col,
        schema.date_col,
        schema.outcome_col,
        schema.base_probability_col,
        entity.id_col,
        *condition.source_cols,
    }
    if entity.label_col is not None:
        required.add(entity.label_col)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise KeyError(f"conditional aptitude columns are missing: {missing}")

    prepared = pd.DataFrame(index=frame.index)
    for column in schema.key_cols:
        prepared[column] = frame[column]
    prepared["race_id"] = frame[schema.race_id_col].astype("string")
    prepared["date"] = pd.to_datetime(frame[schema.date_col], errors="coerce").dt.tz_localize(None)
    prepared["outcome"] = pd.to_numeric(frame[schema.outcome_col], errors="coerce")
    prepared["base_probability"] = pd.to_numeric(
        frame[schema.base_probability_col], errors="coerce"
    )
    prepared["entity_id"] = frame[entity.id_col].astype("string").str.strip()
    prepared["condition_id"] = materialize_condition(frame, condition)
    if entity.label_col is None:
        prepared["entity_label"] = prepared["entity_id"]
    else:
        prepared["entity_label"] = frame[entity.label_col].astype("string").str.strip()

    if prepared[["race_id", "date", "outcome", "base_probability"]].isna().any().any():
        raise ValueError("conditional aptitude input contains null or invalid core values")
    if prepared[["entity_id", "entity_label", "condition_id"]].isna().any().any():
        raise ValueError("conditional aptitude categories contain null values")
    if (prepared[["entity_id", "entity_label", "condition_id"]] == "").any().any():
        raise ValueError("conditional aptitude categories contain empty values")
    if not set(prepared["outcome"].unique().tolist()).issubset({0, 1}):
        raise ValueError("conditional aptitude outcome must contain only 0 and 1")
    if not prepared["base_probability"].between(0.0, 1.0, inclusive="neither").all():
        raise ValueError("base probability must be strictly between 0 and 1")
    return prepared.reset_index(drop=True)


def screen_pair(
    discovery: pd.DataFrame,
    screening: pd.DataFrame,
    *,
    pair_id: str,
    entity: EntitySpec,
    policy: ScreeningPolicy,
) -> PairScreenResult:
    policy.validate()
    if discovery.empty or screening.empty:
        raise ValueError(f"discovery and screening windows must not be empty: {pair_id}")
    n_entities = int(discovery["entity_id"].nunique())
    n_conditions = int(discovery["condition_id"].nunique())
    n_cells = n_entities * n_conditions
    if n_cells > policy.max_cells:
        raise ValueError(
            f"pair exceeds max_cells ({n_cells} > {policy.max_cells}): {pair_id}"
        )

    fit = fit_empirical_bayes_interactions(
        discovery,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        entity_label_col="entity_label",
        main_penalty=policy.main_penalty,
        min_entity_total_n=entity.min_total_n,
        min_condition_levels=entity.min_condition_levels,
        min_cell_n_for_claim=policy.min_cell_n_for_claim,
        practical_delta_probability=policy.practical_delta_probability,
        local_probability_threshold=policy.local_probability_threshold,
    )
    y = screening["outcome"].to_numpy(dtype=float)
    p0 = fit.model.main_model.predict_proba(
        base_probability=screening["base_probability"].to_numpy(dtype=float),
        entity=screening["entity_id"],
        condition=screening["condition_id"],
    )
    p1 = fit.model.predict_proba(
        base_probability=screening["base_probability"].to_numpy(dtype=float),
        entity=screening["entity_id"],
        condition=screening["condition_id"],
    )
    delta_logloss = binary_log_loss(y, p1) - binary_log_loss(y, p0)
    delta_brier = binary_brier_score(y, p1) - binary_brier_score(y, p0)
    eligible = bool(
        fit.eligible_coverage >= policy.min_eligible_coverage
        and fit.interaction_rms_probability >= policy.practical_delta_probability
        and delta_logloss < 0.0
    )
    summary: dict[str, object] = {
        "pair_id": pair_id,
        "status": "eligible" if eligible else "screened_out",
        "discovery_n": len(discovery),
        "screening_n": len(screening),
        "n_entities": n_entities,
        "n_conditions": n_conditions,
        "n_cells": n_cells,
        "tau_logodds": fit.model.tau_logodds,
        "eligible_coverage": fit.eligible_coverage,
        "interaction_rms_probability": fit.interaction_rms_probability,
        "reliable_cell_count": fit.reliable_cell_count,
        "reliable_exposure_share": fit.reliable_exposure_share,
        "screen_delta_logloss": delta_logloss,
        "screen_delta_brier": delta_brier,
        "selected": False,
    }
    cell_effects = fit.cell_effects.copy()
    cell_effects.insert(0, "pair_id", pair_id)
    return PairScreenResult(summary=summary, cell_effects=cell_effects, fit=fit)


def confirm_pair(
    frame: pd.DataFrame,
    *,
    pair_id: str,
    validation_start: str | pd.Timestamp,
    validation_end: str | pd.Timestamp,
    practical_interaction_rms: float,
    policy: ConfirmationPolicy,
) -> PairConfirmationResult:
    policy.validate()
    folds = build_expanding_window_folds(
        frame["date"],
        validation_start=validation_start,
        validation_end=validation_end,
        validation_months=policy.validation_months,
        step_months=policy.step_months,
    )
    if len(folds) < policy.min_folds:
        return _inconclusive_confirmation_result(
            pair_id=pair_id,
            practical_interaction_rms=practical_interaction_rms,
            reason="insufficient_folds",
            fold_count=len(folds),
            bootstrap_block_count=0,
        )

    fold_rows: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []
    stability_frames: list[pd.DataFrame] = []
    for fold in folds:
        selected_penalty = _select_interaction_penalty(
            frame,
            outer_validation_start=fold.validation_start,
            policy=policy,
        )
        train = frame.iloc[fold.train_positions]
        validation = frame.iloc[fold.validation_positions]
        m0 = _fit_model(train, policy=policy, interaction_penalty=None)
        m1 = _fit_model(train, policy=policy, interaction_penalty=selected_penalty)
        y = validation["outcome"].to_numpy(dtype=float)
        base = validation["base_probability"].to_numpy(dtype=float)
        p0 = m0.predict_proba(
            base_probability=base,
            entity=validation["entity_id"],
            condition=validation["condition_id"],
        )
        p1 = m1.predict_proba(
            base_probability=base,
            entity=validation["entity_id"],
            condition=validation["condition_id"],
        )
        delta_logloss = binary_log_loss(y, p1) - binary_log_loss(y, p0)
        delta_brier = binary_brier_score(y, p1) - binary_brier_score(y, p0)
        fold_rows.append(
            {
                "pair_id": pair_id,
                "fold_id": fold.fold_id,
                "train_end": fold.train_end,
                "validation_start": fold.validation_start,
                "validation_end": fold.validation_end,
                "train_n": len(train),
                "validation_n": len(validation),
                "interaction_penalty": selected_penalty,
                "delta_logloss": delta_logloss,
                "delta_brier": delta_brier,
            }
        )
        prediction_frames.append(
            _build_prediction_frame(
                validation,
                pair_id=pair_id,
                fold_id=fold.fold_id,
                y=y,
                p0=p0,
                p1=p1,
            )
        )
        stability_frames.append(
            _build_fold_stability(m1, pair_id=pair_id, fold_id=fold.fold_id)
        )

    fold_metrics = pd.DataFrame(fold_rows)
    oos_predictions = pd.concat(prediction_frames, ignore_index=True)
    race_level, blocks = _race_level_prediction_differences(oos_predictions)
    bootstrap_block_count = int(blocks.nunique())
    stability = _summarize_cell_stability(
        pd.concat(stability_frames, ignore_index=True)
    )
    if bootstrap_block_count < policy.min_bootstrap_blocks:
        return _inconclusive_confirmation_result(
            pair_id=pair_id,
            practical_interaction_rms=practical_interaction_rms,
            reason="insufficient_bootstrap_blocks",
            fold_count=len(fold_metrics),
            bootstrap_block_count=bootstrap_block_count,
            fold_metrics=fold_metrics,
            oos_predictions=oos_predictions,
            cell_stability=stability,
            delta_logloss=float(race_level["logloss_diff"].mean()),
            delta_brier=float(race_level["brier_diff"].mean()),
        )
    logloss_interval, brier_interval = _bootstrap_prediction_differences(
        race_level,
        blocks=blocks,
        policy=policy,
    )
    fold_win_rate = float((fold_metrics["delta_logloss"] < 0.0).mean())
    decision = _decide_confirmation(
        logloss_interval=logloss_interval,
        fold_win_rate=fold_win_rate,
        practical_interaction_rms=practical_interaction_rms,
        policy=policy,
    )
    summary: dict[str, object] = {
        "pair_id": pair_id,
        "decision": decision,
        "inconclusive_reason": None,
        "fold_count": len(fold_metrics),
        "bootstrap_block_count": bootstrap_block_count,
        "fold_win_rate": fold_win_rate,
        "interaction_rms_probability": practical_interaction_rms,
        "delta_logloss": logloss_interval.estimate,
        "delta_logloss_low": logloss_interval.low,
        "delta_logloss_high": logloss_interval.high,
        "probability_logloss_improves": logloss_interval.probability_below_zero,
        "delta_brier": brier_interval.estimate,
        "delta_brier_low": brier_interval.low,
        "delta_brier_high": brier_interval.high,
    }
    return PairConfirmationResult(
        summary=summary,
        fold_metrics=fold_metrics,
        oos_predictions=oos_predictions,
        cell_stability=stability,
    )


def _select_interaction_penalty(
    frame: pd.DataFrame,
    *,
    outer_validation_start: pd.Timestamp,
    policy: ConfirmationPolicy,
) -> float:
    train_positions, validation_positions = build_inner_tuning_split(
        frame["date"],
        outer_validation_start=outer_validation_start,
        tuning_months=policy.tuning_months,
    )
    fallback = float(policy.interaction_penalty_grid[len(policy.interaction_penalty_grid) // 2])
    if not len(train_positions) or not len(validation_positions):
        return fallback
    train = frame.iloc[train_positions]
    validation = frame.iloc[validation_positions]
    y = validation["outcome"].to_numpy(dtype=float)
    scores: list[tuple[float, float]] = []
    for penalty in policy.interaction_penalty_grid:
        model = _fit_model(train, policy=policy, interaction_penalty=float(penalty))
        probability = model.predict_proba(
            base_probability=validation["base_probability"].to_numpy(dtype=float),
            entity=validation["entity_id"],
            condition=validation["condition_id"],
        )
        scores.append((binary_log_loss(y, probability), float(penalty)))
    return min(scores, key=lambda item: (item[0], -item[1]))[1]


def _fit_model(
    frame: pd.DataFrame,
    *,
    policy: ConfirmationPolicy,
    interaction_penalty: float | None,
) -> InteractionLogisticModel:
    return fit_regularized_interaction_logistic(
        frame,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        main_penalty=policy.main_penalty,
        interaction_penalty=interaction_penalty,
    )


def _build_prediction_frame(
    validation: pd.DataFrame,
    *,
    pair_id: str,
    fold_id: int,
    y: np.ndarray,
    p0: np.ndarray,
    p1: np.ndarray,
) -> pd.DataFrame:
    result = validation[["race_id", "date", "entity_id", "condition_id"]].copy()
    result.insert(0, "pair_id", pair_id)
    result.insert(1, "fold_id", fold_id)
    result["outcome"] = y
    result["probability_m0"] = p0
    result["probability_m1"] = p1
    clipped_m0 = np.clip(p0, 1e-12, 1.0 - 1e-12)
    clipped_m1 = np.clip(p1, 1e-12, 1.0 - 1e-12)
    result["logloss_diff"] = -(
        y * np.log(clipped_m1) + (1.0 - y) * np.log1p(-clipped_m1)
    ) + (y * np.log(clipped_m0) + (1.0 - y) * np.log1p(-clipped_m0))
    result["brier_diff"] = np.square(p1 - y) - np.square(p0 - y)
    return result


def _race_level_prediction_differences(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    race_level = (
        predictions.groupby("race_id", observed=True, as_index=False)
        .agg(
            date=("date", "min"),
            logloss_diff=("logloss_diff", "mean"),
            brier_diff=("brier_diff", "mean"),
        )
        .sort_values("date")
    )
    blocks = race_level["date"].dt.to_period("W-MON").astype("string")
    return race_level, blocks


def _bootstrap_prediction_differences(
    race_level: pd.DataFrame,
    *,
    blocks: pd.Series,
    policy: ConfirmationPolicy,
) -> tuple[BootstrapInterval, BootstrapInterval]:
    common = {
        "blocks": blocks,
        "repetitions": policy.bootstrap_repetitions,
        "confidence_level": policy.confidence_level,
    }
    logloss_interval = block_bootstrap_mean(
        race_level["logloss_diff"].to_numpy(dtype=float),
        random_seed=policy.random_seed,
        **common,
    )
    brier_interval = block_bootstrap_mean(
        race_level["brier_diff"].to_numpy(dtype=float),
        random_seed=policy.random_seed + 1,
        **common,
    )
    return logloss_interval, brier_interval


def _inconclusive_confirmation_result(
    *,
    pair_id: str,
    practical_interaction_rms: float,
    reason: str,
    fold_count: int,
    bootstrap_block_count: int,
    fold_metrics: pd.DataFrame | None = None,
    oos_predictions: pd.DataFrame | None = None,
    cell_stability: pd.DataFrame | None = None,
    delta_logloss: float = float("nan"),
    delta_brier: float = float("nan"),
) -> PairConfirmationResult:
    resolved_fold_metrics = (
        pd.DataFrame() if fold_metrics is None else fold_metrics
    )
    if resolved_fold_metrics.empty:
        fold_win_rate = float("nan")
    else:
        fold_win_rate = float(
            (resolved_fold_metrics["delta_logloss"] < 0.0).mean()
        )
    return PairConfirmationResult(
        summary={
            "pair_id": pair_id,
            "decision": "inconclusive",
            "inconclusive_reason": reason,
            "fold_count": fold_count,
            "bootstrap_block_count": bootstrap_block_count,
            "fold_win_rate": fold_win_rate,
            "interaction_rms_probability": practical_interaction_rms,
            "delta_logloss": delta_logloss,
            "delta_logloss_low": float("nan"),
            "delta_logloss_high": float("nan"),
            "probability_logloss_improves": float("nan"),
            "delta_brier": delta_brier,
            "delta_brier_low": float("nan"),
            "delta_brier_high": float("nan"),
        },
        fold_metrics=resolved_fold_metrics,
        oos_predictions=(
            pd.DataFrame() if oos_predictions is None else oos_predictions
        ),
        cell_stability=(
            pd.DataFrame() if cell_stability is None else cell_stability
        ),
    )


def _decide_confirmation(
    *,
    logloss_interval: BootstrapInterval,
    fold_win_rate: float,
    practical_interaction_rms: float,
    policy: ConfirmationPolicy,
) -> Decision:
    if practical_interaction_rms < policy.practical_delta_probability:
        return "rejected"
    if logloss_interval.high < 0.0 and fold_win_rate >= policy.min_fold_win_rate:
        return "confirmed"
    if logloss_interval.low >= 0.0:
        return "rejected"
    return "inconclusive"


def _build_fold_stability(
    model: InteractionLogisticModel,
    *,
    pair_id: str,
    fold_id: int,
) -> pd.DataFrame:
    centered = model.centered_interaction_effects()
    rows = []
    for entity_idx, entity_id in enumerate(model.entity_levels):
        for condition_idx, condition_id in enumerate(model.condition_levels):
            if model.cell_counts[entity_idx, condition_idx] == 0:
                continue
            rows.append(
                {
                    "pair_id": pair_id,
                    "fold_id": fold_id,
                    "entity_id": entity_id,
                    "condition_id": condition_id,
                    "effect_logodds": centered[entity_idx, condition_idx],
                    "train_cell_n": model.cell_counts[entity_idx, condition_idx],
                }
            )
    return pd.DataFrame(rows)


def _summarize_cell_stability(stability: pd.DataFrame) -> pd.DataFrame:
    if stability.empty:
        return stability

    def summarize(group: pd.DataFrame) -> pd.Series:
        effects = group["effect_logodds"].to_numpy(dtype=float)
        nonzero = effects[np.abs(effects) > 1e-12]
        if len(nonzero):
            sign_stability = max(float(np.mean(nonzero > 0.0)), float(np.mean(nonzero < 0.0)))
        else:
            sign_stability = 0.0
        return pd.Series(
            {
                "fold_count": len(group),
                "effect_logodds_mean": float(np.mean(effects)),
                "effect_logodds_low": float(np.quantile(effects, 0.025)),
                "effect_logodds_high": float(np.quantile(effects, 0.975)),
                "sign_stability": sign_stability,
                "latest_train_cell_n": int(group.sort_values("fold_id")["train_cell_n"].iloc[-1]),
                "effect_at_probability_20pct": float(
                    expit(_logit_scalar(0.20) + np.mean(effects)) - 0.20
                ),
            }
        )

    return (
        stability.groupby(
            ["pair_id", "entity_id", "condition_id"],
            observed=True,
            sort=False,
        )
        .apply(summarize, include_groups=False)
        .reset_index()
        .sort_values(["sign_stability", "latest_train_cell_n"], ascending=False)
        .reset_index(drop=True)
    )


def _logit_scalar(probability: float) -> float:
    value = float(np.clip(probability, 1e-12, 1.0 - 1e-12))
    return float(np.log(value / (1.0 - value)))
