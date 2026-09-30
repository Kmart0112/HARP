"""Model-independent binary calibration calculations; no plotting or I/O."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


@dataclass(frozen=True)
class OddsBandReport:
    metrics: pd.DataFrame
    bins: pd.DataFrame
    coverage: dict
    metadata: dict


@dataclass(frozen=True)
class CalibrationReport:
    bins: pd.DataFrame
    histogram: pd.DataFrame
    metrics: dict
    metadata: dict
    predictions: pd.DataFrame | None = None
    odds_bands: OddsBandReport | None = None


def calculate_calibration(samples: pd.DataFrame, *, n_bins: int = 10,
                          strategy: str = "quantile", metadata: dict | None = None) -> CalibrationReport:
    """One actual entrant per row; unknown labels are counted, never made negative.

    Internal bin edges belong to the lower bin, as in sklearn.calibration_curve.
    Quantile ties stay together; empty bins are omitted from the curve.
    """
    if type(n_bins) is not int or n_bins < 1:
        raise ValueError("n_bins must be a positive integer")
    if strategy not in {"quantile", "uniform"}:
        raise ValueError("strategy must be quantile or uniform")
    if not {"y_true", "probability"} <= set(samples.columns):
        raise ValueError("calibration requires y_true and probability columns")
    keys = [key for key in ("race_id", "kettonum") if key in samples]
    if len(keys) == 2 and (samples[keys].isna().any().any() or samples.duplicated(keys).any()):
        raise ValueError("calibration sample IDs must be nonmissing and unique")
    p_all = pd.to_numeric(samples.probability, errors="raise").to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(p_all).all() or ((p_all < 0) | (p_all > 1)).any():
        raise ValueError("probabilities must be finite and in [0, 1]")
    known = samples.y_true.notna().to_numpy()
    y = pd.to_numeric(samples.loc[known, "y_true"], errors="raise").to_numpy(dtype=float)
    if not len(y):
        raise ValueError("calibration has no labelled samples")
    if not np.isin(y, [0, 1]).all():
        raise ValueError("labels must be binary 0/1")
    p = p_all[known]
    edges = (np.quantile(p, np.linspace(0, 1, n_bins + 1)) if strategy == "quantile"
             else np.linspace(0, 1, n_bins + 1))
    assignments = np.searchsorted(edges[1:-1], p, side="left")
    rows = []
    for number in np.unique(assignments):
        selected = assignments == number
        rows.append({"bin": int(number), "lower": float(edges[number]), "upper": float(edges[number + 1]),
                     "count": int(selected.sum()), "mean_probability": float(p[selected].mean()),
                     "observed_rate": float(y[selected].mean())})
    hist_count, hist_edges = np.histogram(p, bins=np.linspace(0, 1, n_bins + 1))
    clipped = np.clip(p, 1e-12, 1 - 1e-12)
    metrics = {"samples": len(y), "input_samples": len(samples), "excluded_missing_labels": int((~known).sum()),
               "brier": float(np.mean((p - y) ** 2)),
               "logloss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log1p(-clipped))),
               "mean_probability": float(p.mean()), "observed_rate": float(y.mean())}
    metrics.update(positives=int(y.sum()), races=int(samples.loc[known, "race_id"].nunique()) if "race_id" in samples else None,
                   gap=float(y.mean() - p.mean()), auc=float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None)
    return CalibrationReport(pd.DataFrame(rows), pd.DataFrame({"lower": hist_edges[:-1],
                             "upper": hist_edges[1:], "count": hist_count}), metrics,
                             {**(metadata or {}), "n_bins": n_bins, "strategy": strategy,
                              "effective_bins": len(rows), "weighting": "entrant",
                              "logloss_clip_epsilon": 1e-12}, samples.copy(deep=True))
