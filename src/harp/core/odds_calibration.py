"""Calibration by odds band on an explicitly covered subset of predictions."""
from dataclasses import replace

import numpy as np
import pandas as pd

from harp.core.calibration import CalibrationReport, OddsBandReport, calculate_calibration
from harp.core.inference.ev_calculator import PlaceOddsMethod, select_place_odds
from harp.core.odds import OddsBatch, normalize_entry_keys


DEFAULT_CALIBRATION_ODDS_BOUNDS = (1., 1.4, 1.8, 2.5, 4., 7., 10., 50., float("inf"))


def add_odds_band_report(report: CalibrationReport, odds: OddsBatch, *, market="place", place_method="midpoint",
                         bounds=DEFAULT_CALIBRATION_ODDS_BOUNDS, min_samples_per_bin=30,
                         odds_metadata=None) -> CalibrationReport:
    if report.predictions is None:
        raise ValueError("odds bands require entrant-level predictions")
    if market not in {"win", "place"}:
        raise ValueError("odds market must be win or place")
    method = PlaceOddsMethod(place_method)
    edges = np.asarray(bounds, dtype=float)
    if (edges.ndim != 1 or len(edges) < 2 or edges[0] != 1 or edges[-1] != np.inf
            or not np.isfinite(edges[:-1]).all() or not (np.diff(edges) > 0).all()):
        raise ValueError("odds bounds must increase strictly from 1 to inf")
    if type(min_samples_per_bin) is not int or min_samples_per_bin < 1:
        raise ValueError("min_samples_per_bin must be a positive integer")
    samples = normalize_entry_keys(report.predictions, name="calibration predictions")
    if "kettonum" in samples and (samples.kettonum.isna().any() or samples.duplicated(["race_id", "kettonum"]).any()):
        raise ValueError("prediction horse identities must be unique")
    quotes = odds.frame
    quote_columns = ["race_id", "horse_number", "win_odds", "place_low", "place_high", "win_status", "place_status"]
    merged = samples.merge(quotes[quote_columns], how="left", on=["race_id", "horse_number"], validate="one_to_one")
    status = merged["win_status" if market == "win" else "place_status"].fillna("unmatched_entry")
    prices = (merged.win_odds.to_numpy(dtype=float) if market == "win" else
              select_place_odds(merged.place_low, merged.place_high, method))
    known = merged.y_true.notna()
    available = status.eq("available") & known
    if (~np.isfinite(prices[available]) | (prices[available] < 1)).any():
        raise ValueError("available odds must be finite and at least 1")
    covered = merged.loc[available, samples.columns].copy()
    covered["evaluation_odds"] = prices[available]
    covered["odds_band"] = np.searchsorted(edges[1:-1], covered.evaluation_odds, side="right")
    rows, curves = [], []
    for index in range(len(edges) - 1):
        upper = "+inf" if np.isinf(edges[index+1]) else f"{edges[index+1]:g}"
        label = f"[{edges[index]:g}, {upper})"
        part = covered.loc[covered.odds_band.eq(index)]
        count = len(part)
        row = {"band": index, "odds_band": label, "lower": float(edges[index]),
               "upper": float(edges[index+1]), "samples": count, "races": 0, "positives": 0,
               "mean_odds": None, "mean_probability": None, "observed_rate": None,
               "gap": None, "brier": None, "logloss": None, "auc": None,
               "status": "empty" if not count else "small_sample" if count < min_samples_per_bin else "ok"}
        if count:
            bin_count = max(1, min(report.metadata["n_bins"], count // min_samples_per_bin))
            part_report = calculate_calibration(part, n_bins=bin_count, strategy=report.metadata["strategy"])
            for name in ("races", "positives", "mean_probability", "observed_rate", "gap", "brier", "logloss", "auc"):
                row[name] = part_report.metrics[name]
            row["mean_odds"] = float(part.evaluation_odds.mean())
            curves.append(part_report.bins.assign(band=index, odds_band=label))
        rows.append(row)
    matched = calculate_calibration(covered, n_bins=report.metadata["n_bins"],
                                    strategy=report.metadata["strategy"]).metrics if len(covered) else None
    reasons = {str(key): int(count) for key, count in status.loc[known & ~available].value_counts().items()}
    coverage = {"labelled_samples": int(known.sum()), "available_samples": len(covered),
                "available_fraction": len(covered) / int(known.sum()), "excluded_by_reason": reasons,
                "matched_overall_metrics": matched,
                "status": "ok" if len(covered) else "no_available_odds"}
    details = {**(odds_metadata or {}), "market": market,
               "place_method": method.value if market == "place" else None,
               "bounds": [float(x) if np.isfinite(x) else "+inf" for x in edges],
               "interval": "left_closed_right_open", "min_samples_per_bin": min_samples_per_bin,
               "policy": odds.policy.to_dict(), "availability_basis": odds.availability_basis,
               "contract_version": odds.contract_version}
    curve_columns = ["bin", "lower", "upper", "count", "mean_probability", "observed_rate", "band", "odds_band"]
    band_report = OddsBandReport(pd.DataFrame(rows), pd.concat(curves, ignore_index=True) if curves else
                                pd.DataFrame(columns=curve_columns), coverage, details)
    return replace(report, odds_bands=band_report)


def validate_odds_entry_identity(predictions: pd.DataFrame, odds_entries: pd.DataFrame) -> None:
    """Check both horse identity and number when an external snapshot provides them."""
    samples = normalize_entry_keys(predictions, name="prediction identities")
    entries = normalize_entry_keys(odds_entries, name="snapshot identities")
    if "held_date" in samples and "held_date" in entries:
        dates = samples[["race_id", "horse_number", "held_date"]].merge(
            entries[["race_id", "horse_number", "held_date"]], on=["race_id", "horse_number"],
            validate="one_to_one", suffixes=("_prediction", "_odds"))
        left = pd.to_datetime(dates.held_date_prediction, errors="raise")
        right = pd.to_datetime(dates.held_date_odds, errors="raise")
        if left.isna().any() or right.isna().any() or not left.dt.date.equals(right.dt.date):
            raise ValueError("odds race date conflicts with prediction dataset")
    if "kettonum" in samples and "kettonum" in entries:
        matched = samples[["race_id", "horse_number", "kettonum"]].merge(
            entries[["race_id", "horse_number", "kettonum"]], on=["race_id", "horse_number"],
            how="inner", validate="one_to_one", suffixes=("_prediction", "_odds"))
        if matched[["kettonum_prediction", "kettonum_odds"]].isna().any().any() or (
                matched.kettonum_prediction.astype(str) != matched.kettonum_odds.astype(str)).any():
            raise ValueError("odds horse identity conflicts with prediction dataset")
