from __future__ import annotations

import pandas as pd


def coerce_numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return series
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    if not pd.api.types.is_object_dtype(series) and not pd.api.types.is_string_dtype(series):
        return series

    ss = series.astype("string")
    extracted = ss.str.extract(r"([+-]?\d+(?:\.\d+)?)", expand=False)
    return pd.to_numeric(extracted, errors="coerce")
