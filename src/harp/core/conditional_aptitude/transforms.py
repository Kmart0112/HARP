from __future__ import annotations

import numpy as np
import pandas as pd

from .specs import ConditionSpec, NumericRange


def materialize_condition(frame: pd.DataFrame, spec: ConditionSpec) -> pd.Series:
    """Build a categorical condition without executing user-defined expressions."""
    spec.validate()
    missing = [column for column in spec.source_cols if column not in frame.columns]
    if missing:
        raise KeyError(f"condition source columns are missing for {spec.key}: {missing}")

    if spec.transform == "identity_category":
        return _as_category_text(frame[spec.source_cols[0]], column=spec.source_cols[0])
    if spec.transform == "fixed_ranges":
        return _materialize_ranges(frame[spec.source_cols[0]], spec.ranges)
    if spec.transform == "cross_category":
        return _cross_text_columns(frame, spec.source_cols, separator=spec.separator)
    if spec.transform == "cross_fixed_ranges":
        category_cols = spec.source_cols[:-1]
        numeric_col = spec.source_cols[-1]
        category_parts = [
            _as_category_text(frame[column], column=column)
            for column in category_cols
        ]
        range_part = _materialize_ranges(frame[numeric_col], spec.ranges)
        return _encode_components(
            [*category_parts, range_part],
            separator=spec.separator,
        )
    raise ValueError(f"unsupported condition transform: {spec.transform}")


def _cross_text_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    *,
    separator: str,
) -> pd.Series:
    parts = [_as_category_text(frame[column], column=column) for column in columns]
    return _encode_components(parts, separator=separator)


def _encode_components(
    parts: list[pd.Series],
    *,
    separator: str,
) -> pd.Series:
    """Length-prefix components so separator characters cannot merge tuples."""
    encoded_parts = [
        part.str.len().astype("string").str.cat(part, sep=":")
        for part in parts
    ]
    result = encoded_parts[0]
    for part in encoded_parts[1:]:
        result = result.str.cat(part, sep=separator)
    return result


def _as_category_text(series: pd.Series, *, column: str) -> pd.Series:
    result = series.astype("string")
    result = result.str.strip()
    if result.isna().any() or (result == "").any():
        raise ValueError(f"condition column contains null or empty values: {column}")
    return result


def _materialize_ranges(
    series: pd.Series,
    ranges: tuple[NumericRange, ...],
) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError(f"numeric condition contains invalid values: {series.name}")

    result = pd.Series(pd.NA, index=series.index, dtype="string")
    value_array = values.to_numpy(dtype=float)
    for numeric_range in ranges:
        lower_mask = np.ones(len(values), dtype=bool)
        upper_mask = np.ones(len(values), dtype=bool)
        if numeric_range.lower is not None:
            lower_mask = value_array >= float(numeric_range.lower)
        if numeric_range.upper is not None:
            upper_mask = value_array <= float(numeric_range.upper)
        mask = lower_mask & upper_mask
        result.loc[mask] = numeric_range.label

    if result.isna().any():
        sample = values.loc[result.isna()].head(5).tolist()
        raise ValueError(f"numeric condition values do not match any configured range: {sample}")
    return result
