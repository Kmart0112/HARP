from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ...dataset_builder import BinaryDataset
from ...metrics import calc_binary_metrics


def build_time_series_folds(
    held_year: np.ndarray,
    race_id: pd.Series,
    train_year_start: int,
    train_year_end: int,
    valid_years_back: int = 5,
) -> list[tuple[np.ndarray, np.ndarray, int]]:
    valid_year_start = int(train_year_end) - int(valid_years_back)
    valid_years = list(range(max(valid_year_start, int(train_year_start) + 1), int(train_year_end)))
    fold_specs: list[tuple[np.ndarray, np.ndarray, int]] = []
    for year in valid_years:
        tr_i = np.where(held_year < year)[0]
        va_i = np.where(held_year == year)[0]
        if len(tr_i) == 0 or len(va_i) == 0:
            continue
        tr_race = set(race_id.iloc[tr_i].tolist())
        va_race = set(race_id.iloc[va_i].tolist())
        overlap = tr_race & va_race
        if overlap:
            raise RuntimeError(f"race_id leakage detected: valid_year={year}, overlap={len(overlap)}")
        fold_specs.append((tr_i, va_i, int(year)))
    return fold_specs


def fit_platt_logodds_oof(
    model: Any,
    ds: BinaryDataset,
    df_meta: pd.DataFrame,
    odds_col: str,
    train_year_start: int,
    train_year_end: int,
    valid_years_back: int = 5,
    eps: float = 1e-12,
) -> dict[str, Any]:
    if not ds.X_tr.index.isin(df_meta.index).all():
        raise KeyError("対象列欠損: df_meta must include rows for training index")

    meta = df_meta.loc[ds.X_tr.index].copy()
    if "race_id" not in meta.columns:
        raise KeyError("対象列欠損: race_id")
    if odds_col not in meta.columns:
        raise KeyError(f"対象列欠損: {odds_col}")

    if "held_year" in meta.columns:
        held_year = pd.to_numeric(meta["held_year"], errors="coerce")
    elif "held_date" in meta.columns:
        held_year = pd.to_datetime(meta["held_date"], errors="coerce").dt.year
    else:
        raise KeyError("対象列欠損: held_year/held_date")
    if held_year.isna().any():
        raise ValueError("年分割不能: held_year conversion failed")

    race_id = meta["race_id"].astype(str).reset_index(drop=True)
    held_year_np = held_year.astype(int).to_numpy()
    odds = pd.to_numeric(meta[odds_col], errors="coerce").astype(float)
    odds = odds.fillna(odds.median()).clip(lower=eps).to_numpy()

    folds = build_time_series_folds(
        held_year=held_year_np,
        race_id=race_id,
        train_year_start=train_year_start,
        train_year_end=train_year_end,
        valid_years_back=valid_years_back,
    )

    y_np = np.asarray(ds.y_tr, dtype=int)
    oof_raw = np.full(shape=(len(ds.X_tr),), fill_value=np.nan, dtype=float)
    fold_metrics: list[dict[str, float | int | None]] = []

    if not isinstance(model, lgb.LGBMClassifier):
        raise TypeError(f"Platt calibration requires lgb.LGBMClassifier, got: {type(model)}")

    base_params = model.get_params()
    base_params.setdefault("objective", "binary")
    base_params.setdefault("random_state", 42)
    base_params.setdefault("n_jobs", -1)

    if len(folds) == 0:
        in_sample_raw = model.predict_proba(ds.X_tr)[:, 1].astype(float)
        oof_raw[:] = in_sample_raw
        fold_metrics.append(
            {
                "fold": 0,
                "valid_year": None,
                "n_tr": int(len(ds.X_tr)),
                "n_va": int(len(ds.X_tr)),
                "auc": None,
                "brier": None,
                "logloss": None,
            }
        )
    else:
        for fold, (tr_i, va_i, valid_year) in enumerate(folds, start=1):
            fold_model = lgb.LGBMClassifier(**base_params)
            x_tr_f = ds.X_tr.iloc[tr_i]
            y_tr_f = y_np[tr_i]
            x_va_f = ds.X_tr.iloc[va_i]
            y_va_f = y_np[va_i]

            fold_model.fit(
                x_tr_f,
                y_tr_f,
                eval_set=[(x_va_f, y_va_f)],
                eval_metric="binary_logloss",
                callbacks=[lgb.early_stopping(200, verbose=False)],
                categorical_feature=ds.cat_features,
            )

            proba_va = fold_model.predict_proba(x_va_f)[:, 1].astype(float)
            oof_raw[va_i] = proba_va
            fold_m = calc_binary_metrics(pd.Series(y_va_f), proba_va)
            fold_metrics.append(
                {
                    "fold": int(fold),
                    "valid_year": int(valid_year),
                    "n_tr": int(len(tr_i)),
                    "n_va": int(len(va_i)),
                    "auc": fold_m["auc"],
                    "brier": fold_m["brier"],
                    "logloss": fold_m["logloss"],
                }
            )

    mask = ~np.isnan(oof_raw)
    if int(mask.sum()) == 0:
        raise RuntimeError("年分割不能: platt OOF is empty")

    p = np.clip(oof_raw[mask], eps, 1.0 - eps)
    x_logit = np.log(p / (1.0 - p))
    x_log_odds = np.log(np.clip(odds[mask], eps, None))
    x_platt = np.column_stack([x_logit, x_log_odds])
    y_platt = y_np[mask]

    lr = LogisticRegression(solver="lbfgs", max_iter=2000)
    lr.fit(x_platt, y_platt)

    return {
        "odds_col": odds_col,
        "eps": float(eps),
        "oof_n": int(mask.sum()),
        "oof_missing": int((~mask).sum()),
        "oof_fallback_in_sample": bool(len(folds) == 0),
        "fold_metrics": fold_metrics,
        "platt": {
            "coef": lr.coef_.astype(float).ravel().tolist(),
            "intercept": lr.intercept_.astype(float).ravel().tolist(),
        },
    }


def resolve_platt_info(payload: dict[str, Any]) -> dict[str, Any]:
    calibration = payload.get("calibration")
    if isinstance(calibration, dict):
        method = str(calibration.get("method") or "")
        params = calibration.get("params")
        if method == "platt_logodds" and isinstance(params, dict):
            return params

    raise KeyError("calibration.params is missing in payload for place_platt predict.")


def apply_platt_logodds(
    base_proba: np.ndarray,
    *,
    payload: dict[str, Any],
    df_feat: pd.DataFrame,
    odds_col: str | None = None,
) -> np.ndarray:
    platt_info = resolve_platt_info(payload)

    platt = platt_info.get("platt")
    if not isinstance(platt, dict):
        raise KeyError("calibration.params.platt is missing.")

    coef = np.asarray(platt.get("coef"), dtype=float).reshape(-1)
    intercept_vec = np.asarray(platt.get("intercept"), dtype=float).reshape(-1)
    if coef.shape[0] != 2:
        raise ValueError(f"platt coef must have 2 elements, got: {coef.shape[0]}")

    intercept = float(intercept_vec[0]) if intercept_vec.size > 0 else 0.0
    eps = float(platt_info.get("eps", 1e-12))

    resolved_odds_col = odds_col or str(platt_info.get("odds_col") or "")
    if not resolved_odds_col:
        raise KeyError("odds_col is required for place_platt predict.")
    if resolved_odds_col not in df_feat.columns:
        raise KeyError(f"Missing required odds column for place_platt: {resolved_odds_col}")

    odds = pd.to_numeric(df_feat[resolved_odds_col], errors="coerce").astype(float)
    if odds.isna().all():
        raise ValueError(f"odds column is all NaN: {resolved_odds_col}")
    if odds.isna().any():
        odds = odds.fillna(float(odds.median()))

    p = np.clip(np.asarray(base_proba, dtype=float), eps, 1.0 - eps)
    x_logit = np.log(p / (1.0 - p))
    x_log_odds = np.log(np.clip(odds.to_numpy(dtype=float), eps, None))
    logits = coef[0] * x_logit + coef[1] * x_log_odds + intercept
    logits = np.clip(logits, -50.0, 50.0)
    return (1.0 / (1.0 + np.exp(-logits))).astype(float)
