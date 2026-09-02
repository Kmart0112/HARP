from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from harp.core.dtypes import coerce_numeric_series


def _normalize_feature_dtypes(
    features: pd.DataFrame,
    feature_names: list[str],
) -> pd.DataFrame:
    normalized = features.copy()
    for col in feature_names:
        if col in normalized.columns:
            normalized[col] = coerce_numeric_series(normalized[col])

    bad_object_cols = [
        c for c in feature_names
        if c in normalized.columns and pd.api.types.is_object_dtype(normalized[c])
    ]
    if bad_object_cols:
        dtypes = {c: str(normalized[c].dtype) for c in bad_object_cols[:30]}
        raise ValueError(
            "Object dtypes remain after normalization. "
            f"bad={bad_object_cols[:30]} dtypes={dtypes}"
        )
    return normalized


def predict_proba_from_payload(
    model_payload: dict[str, Any],
    df: Any,
) -> np.ndarray:
    model = model_payload.get("model")
    feature_names = model_payload.get("feature_names")

    if model is None:
        raise KeyError("Model payload does not include 'model'.")
    if not isinstance(feature_names, list) or not feature_names:
        raise KeyError("Model payload does not include valid 'feature_names'.")
    if df is None:
        raise ValueError("df is None")

    if isinstance(df, pd.DataFrame):
        df_in = df
    else:
        df_in = pd.DataFrame(df)

    if len(df_in) == 0:
        return np.asarray([], dtype=float)

    missing_cols = [c for c in feature_names if c not in df_in.columns]
    if missing_cols:
        raise KeyError(
            "Missing feature columns for inference. "
            f"missing={missing_cols[:20]} total_missing={len(missing_cols)}"
        )

    features = df_in.loc[:, feature_names]
    if isinstance(features, pd.DataFrame):
        normalized = _normalize_feature_dtypes(features, feature_names=feature_names)
        model_input = normalized.replace({pd.NA: np.nan}).to_numpy(dtype=np.float64)
    else:
        model_input = features

    proba = np.asarray(model.predict_proba(model_input))
    if proba.ndim == 2 and proba.shape[1] >= 2:
        return proba[:, 1].astype(float)
    if proba.ndim == 1:
        return proba.astype(float)
    raise ValueError(f"Unexpected predict_proba output shape: {proba.shape}")
