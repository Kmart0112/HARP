from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .binary_trainer import train_binary_lgbm
from .dataset_builder import BinaryDataset, build_binary_dataset
from .metrics import calc_binary_metrics

_VALID_SPLIT_MODES = {"exact", "manual_bins"}
_VALID_PRIMARY_METRICS = {"auc", "brier", "logloss"}


@dataclass(frozen=True)
class ConditionSplitSpec:
    condition_column: str
    split_mode: str = "exact"
    bin_edges: tuple[float, ...] = ()
    bin_labels: tuple[str, ...] = ()
    include_values: tuple[str, ...] = ()
    exclude_values: tuple[str, ...] = ()
    min_train_rows: int = 1
    min_val_rows: int = 1
    min_test_rows: int = 1
    primary_metric: str = "logloss"


@dataclass(frozen=True)
class ConditionSliceResult:
    condition_value: str
    train_rows: int
    val_rows: int
    test_rows: int
    train_positive_rate: float | None
    val_positive_rate: float | None
    test_positive_rate: float | None
    base_auc: float | None
    base_brier: float | None
    base_logloss: float | None
    local_auc: float | None
    local_brier: float | None
    local_logloss: float | None
    delta_auc: float | None
    delta_brier: float | None
    delta_logloss: float | None
    primary_metric: str
    primary_metric_improved: bool | None
    skip_reason: str | None


@dataclass(frozen=True)
class ConditionExperimentSummary:
    condition_column: str
    split_mode: str
    primary_metric: str
    input_rows: int
    eligible_rows: int
    total_slices: int
    base_evaluated_slices: int
    compared_slices: int
    skipped_slices: int
    total_test_rows: int
    compared_test_rows: int
    improved_slices: int
    improved_test_rows: int
    weighted_base_auc: float | None
    weighted_base_brier: float | None
    weighted_base_logloss: float | None
    weighted_local_auc: float | None
    weighted_local_brier: float | None
    weighted_local_logloss: float | None
    weighted_delta_auc: float | None
    weighted_delta_brier: float | None
    weighted_delta_logloss: float | None


def resolve_condition_values(
    df: pd.DataFrame,
    spec: ConditionSplitSpec,
) -> pd.Series:
    _validate_spec(spec)
    if spec.condition_column not in df.columns:
        raise KeyError(f"condition column not found: {spec.condition_column}")

    raw = df[spec.condition_column]
    if spec.split_mode == "exact":
        labels = raw.astype("string").str.strip()
        return labels.mask(labels == "", pd.NA)

    numeric = pd.to_numeric(raw, errors="coerce")
    edges = list(spec.bin_edges)
    labels = list(spec.bin_labels) if spec.bin_labels else _default_bin_labels(edges)
    cut = pd.cut(
        numeric,
        bins=edges,
        labels=labels,
        include_lowest=True,
        right=True,
    )
    return cut.astype("string")


def run_condition_split_experiment(
    df: pd.DataFrame,
    *,
    spec: ConditionSplitSpec,
    feature_names: list[str],
    cat_features: list[str],
    target_col: str,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
    model_params: Mapping[str, Any],
    fit_kwargs: Mapping[str, Any] | None = None,
) -> tuple[ConditionExperimentSummary, tuple[ConditionSliceResult, ...]]:
    _validate_spec(spec)
    condition_labels = resolve_condition_values(df, spec)
    eligible_mask = _build_eligible_mask(condition_labels, spec)
    eligible_df = df.loc[eligible_mask].copy()
    if eligible_df.empty:
        raise ValueError("No rows remain after applying condition filters.")

    eligible_labels = condition_labels.loc[eligible_mask].astype("string")
    eligible_df["_condition_value"] = eligible_labels

    base_ds = build_binary_dataset(
        df=eligible_df,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col=target_col,
        train_year_start=int(train_year_start),
        train_year_end=int(train_year_end),
        test_year=int(test_year),
    )
    base_result = train_binary_lgbm(
        base_ds,
        model_params=model_params,
        fit_kwargs=_prepare_fit_kwargs(base_ds, fit_kwargs),
    )

    slice_values = _sorted_slice_values(eligible_labels)
    slice_results: list[ConditionSliceResult] = []
    for condition_value in slice_values:
        slice_df = eligible_df.loc[eligible_df["_condition_value"] == condition_value].copy()
        raw_counts = _build_split_counts(
            slice_df,
            train_year_start=int(train_year_start),
            train_year_end=int(train_year_end),
            test_year=int(test_year),
        )
        raw_rates = _build_split_positive_rates(
            slice_df,
            target_col=target_col,
            train_year_start=int(train_year_start),
            train_year_end=int(train_year_end),
            test_year=int(test_year),
        )

        try:
            slice_ds = build_binary_dataset(
                df=slice_df,
                feature_names=feature_names,
                cat_features=cat_features,
                target_col=target_col,
                train_year_start=int(train_year_start),
                train_year_end=int(train_year_end),
                test_year=int(test_year),
            )
        except Exception as exc:
            slice_results.append(
                ConditionSliceResult(
                    condition_value=condition_value,
                    train_rows=raw_counts["train_rows"],
                    val_rows=raw_counts["val_rows"],
                    test_rows=raw_counts["test_rows"],
                    train_positive_rate=raw_rates["train_positive_rate"],
                    val_positive_rate=raw_rates["val_positive_rate"],
                    test_positive_rate=raw_rates["test_positive_rate"],
                    base_auc=None,
                    base_brier=None,
                    base_logloss=None,
                    local_auc=None,
                    local_brier=None,
                    local_logloss=None,
                    delta_auc=None,
                    delta_brier=None,
                    delta_logloss=None,
                    primary_metric=spec.primary_metric,
                    primary_metric_improved=None,
                    skip_reason=str(exc),
                )
            )
            continue

        base_metrics = _evaluate_model_on_dataset(base_result.model, slice_ds)
        skip_reason = _build_skip_reason(slice_ds=slice_ds, spec=spec)
        if skip_reason is not None:
            slice_results.append(
                _build_slice_result(
                    condition_value=condition_value,
                    slice_ds=slice_ds,
                    base_metrics=base_metrics,
                    local_metrics=None,
                    primary_metric=spec.primary_metric,
                    skip_reason=skip_reason,
                )
            )
            continue

        try:
            local_result = train_binary_lgbm(
                slice_ds,
                model_params=model_params,
                fit_kwargs=_prepare_fit_kwargs(slice_ds, fit_kwargs),
            )
        except Exception as exc:
            slice_results.append(
                _build_slice_result(
                    condition_value=condition_value,
                    slice_ds=slice_ds,
                    base_metrics=base_metrics,
                    local_metrics=None,
                    primary_metric=spec.primary_metric,
                    skip_reason=str(exc),
                )
            )
            continue

        slice_results.append(
            _build_slice_result(
                condition_value=condition_value,
                slice_ds=slice_ds,
                base_metrics=base_metrics,
                local_metrics=local_result.metrics,
                primary_metric=spec.primary_metric,
                skip_reason=None,
            )
        )

    summary = _build_experiment_summary(
        spec=spec,
        input_rows=int(len(df)),
        eligible_rows=int(len(eligible_df)),
        slice_results=tuple(slice_results),
    )
    return summary, tuple(slice_results)


def condition_slice_results_to_frame(
    slice_results: tuple[ConditionSliceResult, ...] | list[ConditionSliceResult],
) -> pd.DataFrame:
    rows = [asdict(result) for result in slice_results]
    return pd.DataFrame(rows)


def condition_experiment_summary_to_frame(summary: ConditionExperimentSummary) -> pd.DataFrame:
    return pd.DataFrame([asdict(summary)])


def _validate_spec(spec: ConditionSplitSpec) -> None:
    if not str(spec.condition_column).strip():
        raise ValueError("condition_column must not be empty.")
    if spec.split_mode not in _VALID_SPLIT_MODES:
        raise ValueError(f"Unsupported split_mode: {spec.split_mode}")
    if spec.primary_metric not in _VALID_PRIMARY_METRICS:
        raise ValueError(f"Unsupported primary_metric: {spec.primary_metric}")
    for field_name in ("min_train_rows", "min_val_rows", "min_test_rows"):
        if int(getattr(spec, field_name)) < 0:
            raise ValueError(f"{field_name} must be >= 0")
    if spec.split_mode == "manual_bins":
        if len(spec.bin_edges) < 2:
            raise ValueError("manual_bins requires at least 2 bin edges.")
        if list(spec.bin_edges) != sorted(spec.bin_edges):
            raise ValueError("bin_edges must be sorted in ascending order.")
        if len(set(spec.bin_edges)) != len(spec.bin_edges):
            raise ValueError("bin_edges must not contain duplicates.")
        if spec.bin_labels and len(spec.bin_labels) != len(spec.bin_edges) - 1:
            raise ValueError("bin_labels must have len(bin_edges) - 1 items.")


def _default_bin_labels(edges: list[float]) -> list[str]:
    labels: list[str] = []
    for left, right in zip(edges[:-1], edges[1:]):
        labels.append(f"({left:g}, {right:g}]")
    return labels


def _normalize_condition_values(values: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if value:
            out.append(value)
    return tuple(out)


def _build_eligible_mask(labels: pd.Series, spec: ConditionSplitSpec) -> pd.Series:
    mask = labels.notna()
    include_values = _normalize_condition_values(spec.include_values)
    if include_values:
        mask &= labels.isin(include_values)
    exclude_values = _normalize_condition_values(spec.exclude_values)
    if exclude_values:
        mask &= ~labels.isin(exclude_values)
    return mask


def _extract_held_year(df: pd.DataFrame) -> pd.Series:
    if "held_year" in df.columns:
        held_year = pd.to_numeric(df["held_year"], errors="coerce")
    elif "held_date" in df.columns:
        held_year = pd.to_datetime(df["held_date"], errors="coerce").dt.year
    else:
        raise KeyError("held_year/held_date is required.")
    if held_year.isna().any():
        raise ValueError("held_year contains invalid values.")
    return held_year.astype(int)


def _build_split_counts(
    df: pd.DataFrame,
    *,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
) -> dict[str, int]:
    held_year = _extract_held_year(df)
    train_mask = (held_year >= int(train_year_start)) & (held_year < int(train_year_end))
    val_mask = held_year == int(train_year_end)
    test_mask = held_year == int(test_year)
    return {
        "train_rows": int(train_mask.sum()),
        "val_rows": int(val_mask.sum()),
        "test_rows": int(test_mask.sum()),
    }


def _build_split_positive_rates(
    df: pd.DataFrame,
    *,
    target_col: str,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
) -> dict[str, float | None]:
    held_year = _extract_held_year(df)
    target = pd.to_numeric(df[target_col], errors="coerce")
    if target.isna().any():
        raise ValueError(f"{target_col} contains invalid values.")

    def _mean(mask: pd.Series) -> float | None:
        if not bool(mask.any()):
            return None
        return float(target.loc[mask].mean())

    train_mask = (held_year >= int(train_year_start)) & (held_year < int(train_year_end))
    val_mask = held_year == int(train_year_end)
    test_mask = held_year == int(test_year)
    return {
        "train_positive_rate": _mean(train_mask),
        "val_positive_rate": _mean(val_mask),
        "test_positive_rate": _mean(test_mask),
    }


def _evaluate_model_on_dataset(model: Any, ds: BinaryDataset) -> dict[str, float | None]:
    proba = model.predict_proba(ds.X_test)[:, 1].astype(float)
    return calc_binary_metrics(ds.y_test, proba)


def _prepare_fit_kwargs(
    ds: BinaryDataset,
    fit_kwargs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    resolved = dict(fit_kwargs or {})
    resolved.setdefault("eval_set", [(ds.X_val, ds.y_val)])
    return resolved


def _build_skip_reason(
    *,
    slice_ds: BinaryDataset,
    spec: ConditionSplitSpec,
) -> str | None:
    if len(slice_ds.X_tr) < int(spec.min_train_rows):
        return (
            f"train rows below threshold: {len(slice_ds.X_tr)} < {int(spec.min_train_rows)}"
        )
    if len(slice_ds.X_val) < int(spec.min_val_rows):
        return f"val rows below threshold: {len(slice_ds.X_val)} < {int(spec.min_val_rows)}"
    if len(slice_ds.X_test) < int(spec.min_test_rows):
        return f"test rows below threshold: {len(slice_ds.X_test)} < {int(spec.min_test_rows)}"
    return None


def _build_slice_result(
    *,
    condition_value: str,
    slice_ds: BinaryDataset,
    base_metrics: dict[str, float | None],
    local_metrics: dict[str, float | None] | None,
    primary_metric: str,
    skip_reason: str | None,
) -> ConditionSliceResult:
    local_auc = None if local_metrics is None else local_metrics.get("auc")
    local_brier = None if local_metrics is None else local_metrics.get("brier")
    local_logloss = None if local_metrics is None else local_metrics.get("logloss")
    delta_auc = _metric_delta(local_auc, base_metrics.get("auc"))
    delta_brier = _metric_delta(local_brier, base_metrics.get("brier"))
    delta_logloss = _metric_delta(local_logloss, base_metrics.get("logloss"))
    primary_metric_improved = _is_metric_improved(
        primary_metric=primary_metric,
        base_value=base_metrics.get(primary_metric),
        local_value=None if local_metrics is None else local_metrics.get(primary_metric),
    )
    return ConditionSliceResult(
        condition_value=condition_value,
        train_rows=int(len(slice_ds.X_tr)),
        val_rows=int(len(slice_ds.X_val)),
        test_rows=int(len(slice_ds.X_test)),
        train_positive_rate=_series_mean_or_none(slice_ds.y_tr),
        val_positive_rate=_series_mean_or_none(slice_ds.y_val),
        test_positive_rate=_series_mean_or_none(slice_ds.y_test),
        base_auc=base_metrics.get("auc"),
        base_brier=base_metrics.get("brier"),
        base_logloss=base_metrics.get("logloss"),
        local_auc=local_auc,
        local_brier=local_brier,
        local_logloss=local_logloss,
        delta_auc=delta_auc,
        delta_brier=delta_brier,
        delta_logloss=delta_logloss,
        primary_metric=primary_metric,
        primary_metric_improved=primary_metric_improved,
        skip_reason=skip_reason,
    )


def _series_mean_or_none(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    return float(pd.to_numeric(series, errors="coerce").mean())


def _metric_delta(local_value: float | None, base_value: float | None) -> float | None:
    if local_value is None or base_value is None:
        return None
    return float(local_value) - float(base_value)


def _is_metric_improved(
    *,
    primary_metric: str,
    base_value: float | None,
    local_value: float | None,
) -> bool | None:
    if base_value is None or local_value is None:
        return None
    if primary_metric == "auc":
        return bool(float(local_value) > float(base_value))
    return bool(float(local_value) < float(base_value))


def _sorted_slice_values(labels: pd.Series) -> list[str]:
    unique_values = labels.dropna().astype(str).unique().tolist()
    return sorted(unique_values, key=str)


def _weighted_metric_average(
    slice_results: tuple[ConditionSliceResult, ...],
    *,
    value_attr: str,
) -> tuple[float | None, int]:
    weights: list[int] = []
    values: list[float] = []
    for result in slice_results:
        value = getattr(result, value_attr)
        if value is None or result.local_logloss is None and value_attr.startswith("local_"):
            continue
        if value is None or result.test_rows <= 0:
            continue
        weights.append(int(result.test_rows))
        values.append(float(value))
    if not weights:
        return None, 0
    return float(np.average(values, weights=np.asarray(weights, dtype=float))), int(sum(weights))


def _build_experiment_summary(
    *,
    spec: ConditionSplitSpec,
    input_rows: int,
    eligible_rows: int,
    slice_results: tuple[ConditionSliceResult, ...],
) -> ConditionExperimentSummary:
    base_evaluated_slices = sum(1 for result in slice_results if result.base_logloss is not None)
    compared = tuple(result for result in slice_results if result.local_logloss is not None)
    weighted_base_auc, _ = _weighted_metric_average(compared, value_attr="base_auc")
    weighted_base_brier, _ = _weighted_metric_average(compared, value_attr="base_brier")
    weighted_base_logloss, _ = _weighted_metric_average(compared, value_attr="base_logloss")
    weighted_local_auc, compared_test_rows = _weighted_metric_average(compared, value_attr="local_auc")
    weighted_local_brier, _ = _weighted_metric_average(compared, value_attr="local_brier")
    weighted_local_logloss, _ = _weighted_metric_average(compared, value_attr="local_logloss")
    weighted_delta_auc, _ = _weighted_metric_average(compared, value_attr="delta_auc")
    weighted_delta_brier, _ = _weighted_metric_average(compared, value_attr="delta_brier")
    weighted_delta_logloss, _ = _weighted_metric_average(compared, value_attr="delta_logloss")
    improved_results = tuple(result for result in compared if result.primary_metric_improved is True)
    total_test_rows = int(sum(result.test_rows for result in slice_results))
    return ConditionExperimentSummary(
        condition_column=spec.condition_column,
        split_mode=spec.split_mode,
        primary_metric=spec.primary_metric,
        input_rows=int(input_rows),
        eligible_rows=int(eligible_rows),
        total_slices=len(slice_results),
        base_evaluated_slices=base_evaluated_slices,
        compared_slices=len(compared),
        skipped_slices=sum(1 for result in slice_results if result.skip_reason is not None),
        total_test_rows=total_test_rows,
        compared_test_rows=compared_test_rows,
        improved_slices=len(improved_results),
        improved_test_rows=int(sum(result.test_rows for result in improved_results)),
        weighted_base_auc=weighted_base_auc,
        weighted_base_brier=weighted_base_brier,
        weighted_base_logloss=weighted_base_logloss,
        weighted_local_auc=weighted_local_auc,
        weighted_local_brier=weighted_local_brier,
        weighted_local_logloss=weighted_local_logloss,
        weighted_delta_auc=weighted_delta_auc,
        weighted_delta_brier=weighted_delta_brier,
        weighted_delta_logloss=weighted_delta_logloss,
    )
