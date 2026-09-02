from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from harp.core.dtypes import coerce_numeric_series


@dataclass(frozen=True)
class BinaryDataset:
    X_tr: pd.DataFrame
    y_tr: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series
    feature_names: list[str]
    cat_features: list[str]
    split_info: dict[str, Any]


def build_binary_dataset(
    df: pd.DataFrame,
    feature_names: list[str],
    cat_features: list[str],
    target_col: str,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
) -> BinaryDataset:
    if target_col not in df.columns:
        raise KeyError(f"対象列欠損: {target_col}")

    df_work = df.copy()
    if "held_year" not in df_work.columns:
        if "held_date" not in df_work.columns:
            raise KeyError("対象列欠損: held_year/held_date")
        held_dt = pd.to_datetime(df_work["held_date"], errors="coerce")
        if held_dt.isna().any():
            invalid_rows = int(held_dt.isna().sum())
            raise ValueError(f"年分割不能: held_date parse failure rows={invalid_rows}")
        df_work["held_year"] = held_dt.dt.year.astype(int)

    missing_features = [c for c in feature_names if c not in df_work.columns]
    if missing_features:
        raise KeyError(
            f"不足特徴量: {missing_features[:20]}"
            f"{'...' if len(missing_features) > 20 else ''}"
        )

    y = pd.to_numeric(df_work[target_col], errors="coerce")
    if y.isna().any():
        invalid_rows = int(y.isna().sum())
        raise ValueError(f"対象列欠損: {target_col} has invalid rows={invalid_rows}")
    y = y.astype(int)

    held_year = pd.to_numeric(df_work["held_year"], errors="coerce")
    if held_year.isna().any():
        invalid_rows = int(held_year.isna().sum())
        raise ValueError(f"年分割不能: held_year has invalid rows={invalid_rows}")
    held_year = held_year.astype(int)

    train_mask = (held_year >= int(train_year_start)) & (held_year < int(train_year_end))
    val_mask = held_year == int(train_year_end)
    test_mask = held_year == int(test_year)
    if not train_mask.any() or not val_mask.any() or not test_mask.any():
        raise ValueError(
            "年分割不能: "
            f"train={int(train_mask.sum())}, val={int(val_mask.sum())}, test={int(test_mask.sum())}, "
            f"train_year_start={train_year_start}, train_year_end={train_year_end}, test_year={test_year}"
        )

    X = df_work.loc[:, feature_names].copy()
    cat_set = set(cat_features)
    for col in feature_names:
        if col in cat_set:
            if pd.api.types.is_numeric_dtype(X[col]):
                X[col] = pd.to_numeric(X[col], errors="coerce").astype("Int64").astype("category")
            else:
                X[col] = X[col].astype("string").fillna("__NA__").astype("category")
        else:
            X[col] = coerce_numeric_series(X[col]).astype("float64")

    train_pos = np.flatnonzero(train_mask.to_numpy())
    val_pos = np.flatnonzero(val_mask.to_numpy())
    test_pos = np.flatnonzero(test_mask.to_numpy())

    X_tr = X.iloc[train_pos].copy()
    y_tr = y.iloc[train_pos].copy()
    X_val = X.iloc[val_pos].copy()
    y_val = y.iloc[val_pos].copy()
    X_test = X.iloc[test_pos].copy()
    y_test = y.iloc[test_pos].copy()

    if y_tr.nunique() < 2:
        raise ValueError(
            "target が単一クラス: "
            f"target_col={target_col}, classes={sorted(y_tr.unique().tolist())}"
        )

    split_info = {
        "train_year_start": int(train_year_start),
        "train_year_end": int(train_year_end),
        "test_year": int(test_year),
        "n_train_rows": int(len(X_tr)),
        "n_val_rows": int(len(X_val)),
        "n_test_rows": int(len(X_test)),
    }

    return BinaryDataset(
        X_tr=X_tr,
        y_tr=y_tr,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        feature_names=list(feature_names),
        cat_features=list(cat_features),
        split_info=split_info,
    )
