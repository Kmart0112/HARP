from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from .edge_simulation import prepare_edge_frame


SUPPORTED_FUKUSHO_TYPES = (
    "odds_fukusho_low",
    "odds_fukusho_high",
    "odds_fukusho_avg",
    "odds_fukusho_weighted_avg",
)
FukushoType = Literal[
    "odds_fukusho_low",
    "odds_fukusho_high",
    "odds_fukusho_avg",
    "odds_fukusho_weighted_avg",
]


def make_prediction_frame(
    df_feat: pd.DataFrame,
    probability: np.ndarray,
    probability_col: str = "p_place",
) -> pd.DataFrame:
    if "race_id" not in df_feat.columns or "horse_number" not in df_feat.columns:
        raise KeyError("df_feat must include 'race_id' and 'horse_number'.")

    out = pd.DataFrame(
        {
            "race_id": df_feat["race_id"].astype(str).values,
            "horse_number": pd.to_numeric(df_feat["horse_number"], errors="raise").astype(int),
            probability_col: probability,
        }
    )
    for col in ("held_date", "surface", "distance_m", "horse_name"):
        if col in df_feat.columns:
            out[col] = df_feat[col].values
    return out


def join_odds_and_compute_ev(
    df_pred: pd.DataFrame,
    df_odds: pd.DataFrame,
    probability_col: str = "p_place",
    fukusho_type: FukushoType = "odds_fukusho_avg",
    kelly_fraction: float = 0.1,
    kelly_cap: float = 0.05,
    bankroll: float = 100000.0,
) -> pd.DataFrame:
    base_odds_cols = [
        "race_id",
        "horse_number",
        "odds_fukusho_low",
        "odds_fukusho_high",
        "odds_fukusho_avg",
    ]
    odds_cols = list(dict.fromkeys([*base_odds_cols, fukusho_type]))
    missing_cols = [c for c in odds_cols if c not in df_odds.columns]
    if missing_cols:
        raise KeyError(f"Missing required odds columns: {missing_cols}")

    odds_use = df_odds.loc[:, odds_cols].copy()
    odds_use["race_id"] = odds_use["race_id"].astype(str)
    odds_use["horse_number"] = pd.to_numeric(odds_use["horse_number"], errors="raise").astype(int)

    out = df_pred.merge(odds_use, on=["race_id", "horse_number"], how="left")
    out["odds"] = pd.to_numeric(out[fukusho_type], errors="coerce")
    out = out.dropna(subset=["odds"]).copy()
    out[probability_col] = pd.to_numeric(out[probability_col], errors="coerce")
    out = out.dropna(subset=[probability_col]).copy()

    out = prepare_edge_frame(
        out,
        prob_col=probability_col,
        odds_col="odds",
        market_prob_scale=0.8,
        ev_col="ev",
        ev_profit_col="ev_profit",
        odds_bins=None,
        odds_labels=None,
    )

    out["ev_return"] = out[probability_col] * out["odds"]
    out["ev_profit"] = out["ev_return"] - 1.0
    out["q_mkt"] = out["market_prob"]

    out["kelly_fraction"] = np.where(
        out["odds"] > 1.0,
        kelly_fraction
        * (out[probability_col] * (out["odds"] - 1.0) - (1.0 - out[probability_col]))
        / (out["odds"] - 1.0),
        0.0,
    )
    out["kelly_fraction"] = out["kelly_fraction"].clip(lower=0.0, upper=kelly_cap)
    out["kelly_bet_amount"] = out["kelly_fraction"] * bankroll
    return out
