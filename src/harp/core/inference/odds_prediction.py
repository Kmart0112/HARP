"""Prediction decisions from one validated input batch, independent of storage."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from harp.core.odds import assemble_odds_features, odds_features_available
from harp.core.race_inputs import RaceInputs
from harp.core.training.algorithms.calibration.logit_shift import (
    apply_logit_shift_grouped,
)
from harp.core.training.algorithms.calibration.platt_logodds import apply_platt_odds

from .ev_calculator import PlaceOddsMethod, compute_place_ev, select_place_odds
from .place_predictor import predict_proba_from_payload


@dataclass(frozen=True)
class PlaceEvaluation:
    rows: pd.DataFrame
    shifted_rows: pd.DataFrame | None


def evaluate_place_inputs(
    inputs: RaceInputs, payload: dict, *, use_platt: bool, method: PlaceOddsMethod,
    bankroll: float, kelly_fraction: float, kelly_cap: float,
) -> PlaceEvaluation:
    features = assemble_odds_features(inputs.frame, inputs.odds)
    odds = inputs.odds.align(features)
    model_ready = odds_features_available(features, payload["feature_names"])
    closed = pd.Series(False, index=features.index)
    unknown_start = pd.Series(False, index=features.index)
    if inputs.odds.policy.mode == "latest_before":
        if "scheduled_start_at" not in features:
            raise ValueError("prediction requires scheduled_start_at to exclude closed races")
        starts = pd.to_datetime(features.scheduled_start_at, utc=True, errors="raise")
        unknown_start = starts.isna()
        closed = starts.le(pd.Timestamp(inputs.odds.policy.as_of))
        model_ready &= ~closed & ~unknown_start
    raw = np.full(len(features), np.nan)
    if model_ready.any():
        raw[model_ready] = predict_proba_from_payload(payload, features.loc[model_ready])
    probability = raw.copy()
    status = np.where(model_ready, "predicted", "missing_model_odds").astype(object)
    status[closed] = "race_closed"
    status[unknown_start] = "unknown_start"
    if use_platt:
        calibration_ready = model_ready & odds.win_status.eq("available")
        probability[:] = np.nan
        if calibration_ready.any():
            probability[calibration_ready] = apply_platt_odds(raw[calibration_ready],
                win_odds=odds.loc[calibration_ready, "win_odds"].to_numpy(), payload=payload)
        status[model_ready & ~calibration_ready] = "missing_calibration_odds"
    rows = _evaluate_rows(features, odds, raw, probability, status, method,
                          bankroll=bankroll, kelly_fraction=kelly_fraction, kelly_cap=kelly_cap)
    shifted_rows = None
    if use_platt:
        full_race = pd.Series(np.isfinite(probability)).groupby(features.race_id).transform("all")
        # An explicit count protects against a provider returning a truncated field.
        count_field = "active_entrant_count" if "active_entrant_count" in features else "num_starters"
        if count_field in features:
            actual = features.groupby("race_id").horse_number.transform("size")
            full_race &= pd.to_numeric(features[count_field]).eq(actual)
        shifted = np.full(len(features), np.nan)
        if full_race.any():
            group = features.loc[full_race, "race_id"]
            sizes = group.value_counts()
            k = {race: min(2 if count <= 7 else 3, count) for race, count in sizes.items()}
            shifted[full_race] = apply_logit_shift_grouped(probability[full_race], group.to_numpy(), k_by_group=k)
        shifted_status = np.where(full_race, "predicted", "incomplete_race")
        shifted_rows = _evaluate_rows(features, odds, raw, shifted, shifted_status, method,
                                     bankroll=bankroll, kelly_fraction=kelly_fraction, kelly_cap=kelly_cap)
    return PlaceEvaluation(rows, shifted_rows)


def _evaluate_rows(features, odds, raw, probability, status, method, **stake):
    out = features.copy()
    out["p_raw"] = raw
    out["p_place"] = probability
    out["prediction_status"] = status
    out["odds_status"] = odds.place_status.to_numpy()
    out["ev_status"] = np.where(~np.isfinite(probability), "prediction_unavailable", odds.place_status)
    out["quote_id"] = odds.quote_id.to_numpy()
    out["odds_published_at"] = odds.published_at.to_numpy()
    out["odds_cutoff_at"] = odds.cutoff_at.to_numpy()
    out["odds_fukusho_low"] = odds.place_low.to_numpy()
    out["odds_fukusho_high"] = odds.place_high.to_numpy()
    valid = np.isfinite(probability) & odds.place_status.eq("available").to_numpy()
    out["skip_reason"] = np.where(valid, "", out.ev_status)
    chosen = select_place_odds(odds.place_low, odds.place_high, method)
    ev = compute_place_ev(probability[valid], chosen[valid], **stake)
    ev.index = out.index[valid]
    for column in ev:
        out[column] = ev[column].reindex(out.index)
    out.loc[valid, "ev_status"] = "calculated"
    return out
