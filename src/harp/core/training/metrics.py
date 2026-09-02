from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


def calc_binary_metrics(
    y_true: pd.Series,
    proba: np.ndarray,
) -> dict[str, float | None]:
    y_np = np.asarray(y_true, dtype=int)
    p_np = np.asarray(proba, dtype=float)
    out: dict[str, float | None] = {"auc": None, "brier": None, "logloss": None}

    try:
        if len(np.unique(y_np)) >= 2:
            out["auc"] = float(roc_auc_score(y_np, p_np))
    except Exception:
        out["auc"] = None
    try:
        out["brier"] = float(brier_score_loss(y_np, p_np))
    except Exception:
        out["brier"] = None
    try:
        out["logloss"] = float(log_loss(y_np, np.clip(p_np, 1e-12, 1.0 - 1.0e-12)))
    except Exception:
        out["logloss"] = None

    return out


def make_feature_importance(
    feature_names: pd.Index,
    importance_gain: np.ndarray,
    importance_split: np.ndarray,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "feature": list(feature_names),
            "importance_gain": importance_gain,
            "importance_split": importance_split,
        }
    ).sort_values("importance_gain", ascending=False).reset_index(drop=True)

