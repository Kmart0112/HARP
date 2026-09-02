from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


DEFAULT_ODDS_BINS = [1.1, 1.4, 1.8, 2.5, 4.0, 7.0, 10.0, 50.0, np.inf]
DEFAULT_ODDS_LABELS = [
    "1.1-1.4",
    "1.4-1.8",
    "1.8-2.5",
    "2.5-4.0",
    "4.0-7",
    "7-10",
    "10-50",
    "50+",
]


def _validate_odds_bins_labels(
    odds_bins: list[float],
    odds_labels: list[str] | None,
) -> list[str] | None:
    if len(odds_bins) < 2:
        raise ValueError("odds_bins must include at least two boundaries.")
    if odds_labels is None:
        return None
    if len(odds_labels) != len(odds_bins) - 1:
        raise ValueError(
            "odds_labels length must be len(odds_bins) - 1. "
            f"got labels={len(odds_labels)} bins={len(odds_bins)}"
        )
    return odds_labels


def prepare_edge_frame(
    df: pd.DataFrame,
    *,
    prob_col: str,
    odds_col: str = "odds",
    label_col: str | None = None,
    market_prob_col: str | None = None,
    market_prob_scale: float = 0.8,
    ev_col: str = "ev",
    ev_profit_col: str = "ev_profit",
    realized_payout_col: str | None = None,
    odds_bins: list[float] | None = None,
    odds_labels: list[str] | None = None,
) -> pd.DataFrame:
    """Normalize probability/odds columns and compute edge-related derived columns.

    Returns a frame that always includes:
    - prob, odds, implied_prob, market_prob, edge, ev, odds_band, payout_mult_plan

    Conditionally includes:
    - y (when label_col provided)
    - payout_mult_real (when realized payout is provided or exists)
    """
    if prob_col not in df.columns:
        raise KeyError(f"missing prob_col: {prob_col}")
    if odds_col not in df.columns:
        raise KeyError(f"missing odds_col: {odds_col}")

    out = df.copy()
    out["prob"] = pd.to_numeric(out[prob_col], errors="coerce").astype(float).clip(0.0, 1.0)
    out["odds"] = pd.to_numeric(out[odds_col], errors="coerce").astype(float)
    out = out.dropna(subset=["prob", "odds"]).copy()
    out = out[out["odds"] > 0.0].copy()

    out["implied_prob"] = 1.0 / out["odds"]

    if market_prob_col is not None:
        if market_prob_col not in out.columns:
            raise KeyError(f"missing market_prob_col: {market_prob_col}")
        out["market_prob"] = pd.to_numeric(out[market_prob_col], errors="coerce").astype(float)
        out["market_prob"] = out["market_prob"].fillna(market_prob_scale * out["implied_prob"])
    else:
        out["market_prob"] = market_prob_scale * out["implied_prob"]

    out["market_prob"] = out["market_prob"].clip(0.0, 1.0)
    out["edge"] = out["prob"] - out["market_prob"]

    if ev_col in out.columns:
        out["ev"] = pd.to_numeric(out[ev_col], errors="coerce").astype(float)
    elif ev_profit_col in out.columns:
        out["ev"] = pd.to_numeric(out[ev_profit_col], errors="coerce").astype(float)
    else:
        out["ev"] = out["prob"] * out["odds"] - 1.0

    if label_col is not None:
        if label_col not in out.columns:
            raise KeyError(f"missing label_col: {label_col}")
        out["y"] = pd.to_numeric(out[label_col], errors="coerce").fillna(0).astype(int)

    out["payout_mult_plan"] = out["odds"].astype(float)

    if realized_payout_col is not None:
        if realized_payout_col not in out.columns:
            raise KeyError(f"missing realized_payout_col: {realized_payout_col}")
        out["payout_mult_real"] = (
            pd.to_numeric(out[realized_payout_col], errors="coerce")
            .fillna(0.0)
            .astype(float)
            .clip(lower=0.0)
        )
    elif "payout_mult_real" in out.columns:
        out["payout_mult_real"] = (
            pd.to_numeric(out["payout_mult_real"], errors="coerce")
            .fillna(0.0)
            .astype(float)
            .clip(lower=0.0)
        )
    elif "real_return" in out.columns:
        out["payout_mult_real"] = (
            pd.to_numeric(out["real_return"], errors="coerce")
            .fillna(0.0)
            .astype(float)
            .clip(lower=0.0)
        )

    resolved_bins = list(odds_bins) if odds_bins is not None else list(DEFAULT_ODDS_BINS)
    resolved_labels = _validate_odds_bins_labels(
        resolved_bins,
        list(odds_labels) if odds_labels is not None else list(DEFAULT_ODDS_LABELS),
    )

    out["odds_band"] = pd.cut(
        out["odds"],
        bins=resolved_bins,
        labels=resolved_labels,
        right=True,
        include_lowest=True,
    )
    return out


def filter_edge_candidates(
    df: pd.DataFrame,
    *,
    threshold: float,
    edge_col: str = "edge",
    race_id_col: str = "race_id",
    rank_col: str = "edge",
    rank_desc: bool = True,
) -> pd.DataFrame:
    if edge_col not in df.columns:
        raise KeyError(f"missing edge_col: {edge_col}")
    if race_id_col not in df.columns:
        raise KeyError(f"missing race_id_col: {race_id_col}")
    if rank_col not in df.columns:
        raise KeyError(f"missing rank_col: {rank_col}")

    out = df[pd.to_numeric(df[edge_col], errors="coerce") >= float(threshold)].copy()
    out = out.sort_values(
        [race_id_col, rank_col],
        ascending=[True, not rank_desc],
    )
    return out


def simulate_edge_thresholds(
    df: pd.DataFrame,
    *,
    thresholds: list[float],
    selection_mode: Literal["all", "top_n_per_race"] = "top_n_per_race",
    top_n: int = 1,
    rank_col: str = "edge",
    rank_desc: bool = True,
    edge_col: str = "edge",
    odds_col: str = "odds",
    race_id_col: str = "race_id",
    y_col: str = "y",
    ev_col: str = "ev",
    stake_mode: Literal["flat", "target_payout", "edge_proportional"] = "flat",
    stake: float = 1.0,
    target_payout: float = 1.0,
    edge_unit: float = 0.1,
    stake_at_edge_unit: float = 1.0,
    odds_max: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(thresholds) == 0:
        raise ValueError("thresholds must not be empty.")
    if race_id_col not in df.columns:
        raise KeyError(f"missing race_id_col: {race_id_col}")
    if edge_col not in df.columns:
        raise KeyError(f"missing edge_col: {edge_col}")
    if odds_col not in df.columns:
        raise KeyError(f"missing odds_col: {odds_col}")
    if rank_col not in df.columns:
        raise KeyError(f"missing rank_col: {rank_col}")

    base = df.copy()
    base[edge_col] = pd.to_numeric(base[edge_col], errors="coerce").astype(float)
    base[odds_col] = pd.to_numeric(base[odds_col], errors="coerce").astype(float)
    base = base.dropna(subset=[race_id_col, edge_col, odds_col]).copy()
    base = base[base[odds_col] > 0.0].copy()

    if odds_max is not None:
        base = base[base[odds_col] < float(odds_max)].copy()

    if selection_mode == "top_n_per_race":
        if top_n <= 0:
            raise ValueError("top_n must be positive.")
        base_selected = (
            base.sort_values([race_id_col, rank_col], ascending=[True, not rank_desc])
            .groupby(race_id_col, as_index=False)
            .head(int(top_n))
            .copy()
        )
    elif selection_mode == "all":
        base_selected = base.copy()
    else:
        raise ValueError(f"unsupported selection_mode: {selection_mode}")

    n_pool = len(base_selected)
    summary_rows: list[dict[str, object]] = []
    detail_frames: list[pd.DataFrame] = []

    for threshold in thresholds:
        th = float(threshold)
        bets = base_selected[base_selected[edge_col] >= th].copy()

        if stake_mode == "flat":
            bets["stake"] = float(stake)
        elif stake_mode == "target_payout":
            bets["stake"] = float(target_payout) / bets[odds_col].astype(float).clip(lower=1e-12)
        elif stake_mode == "edge_proportional":
            denom = float(edge_unit) if float(edge_unit) != 0.0 else 1e-12
            bets["stake"] = (
                float(stake_at_edge_unit) * (bets[edge_col].astype(float) / denom)
            ).clip(lower=0.0)
        else:
            raise ValueError(f"unsupported stake_mode: {stake_mode}")

        payout_col = "payout_mult_real" if "payout_mult_real" in bets.columns else odds_col

        if y_col in bets.columns:
            y_values = pd.to_numeric(bets[y_col], errors="coerce").fillna(0).astype(int)
            payout_values = pd.to_numeric(bets[payout_col], errors="coerce").fillna(0.0).astype(float)
            bets["return"] = np.where(y_values == 1, bets["stake"] * payout_values, 0.0)
            bets["profit"] = bets["return"] - bets["stake"]
            hit_rate = float(y_values.mean()) if len(y_values) else np.nan
        else:
            bets["return"] = np.nan
            bets["profit"] = np.nan
            hit_rate = np.nan

        total_stake = float(bets["stake"].sum()) if len(bets) else 0.0
        total_return = float(np.nansum(bets["return"].to_numpy(dtype=float))) if len(bets) else 0.0
        roi = float(total_return / total_stake) if total_stake > 0 else np.nan

        avg_ev = float(pd.to_numeric(bets[ev_col], errors="coerce").mean()) if (ev_col in bets.columns and len(bets)) else np.nan
        avg_edge = float(pd.to_numeric(bets[edge_col], errors="coerce").mean()) if len(bets) else np.nan

        summary_rows.append(
            {
                "threshold": th,
                "selection_mode": selection_mode,
                "stake_mode": stake_mode,
                "top_n": int(top_n),
                "n_pool": int(n_pool),
                "n_bets": int(len(bets)),
                "bets_rate": float(len(bets) / n_pool) if n_pool > 0 else np.nan,
                "total_stake": total_stake,
                "total_return": total_return,
                "total_profit": float(total_return - total_stake),
                "roi": roi,
                "hit_rate": hit_rate,
                "avg_ev": avg_ev,
                "avg_edge": avg_edge,
            }
        )

        bets["threshold"] = th
        detail_frames.append(bets)

    summary_df = pd.DataFrame(summary_rows)
    if detail_frames:
        details_df = pd.concat(detail_frames, ignore_index=True)
    else:
        details_df = pd.DataFrame()

    return summary_df, details_df
