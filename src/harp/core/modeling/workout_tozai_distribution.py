from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
import math

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, mannwhitneyu

from .workout_time_relationships import _coerce_numeric


@dataclass(frozen=True)
class WorkoutTozaiSourceSpec:
    name: str
    label: str
    table_name: str
    date_col: str
    group_col: str
    default_metric_col: str
    metric_cols: tuple[str, ...]


DEFAULT_WORKOUT_TOZAI_SOURCE_SPECS: tuple[WorkoutTozaiSourceSpec, ...] = (
    WorkoutTozaiSourceSpec(
        name="staging.stg_n_hanro",
        label="坂路 raw staging",
        table_name="staging.stg_n_hanro",
        date_col="chokyo_date",
        group_col="tozai_cd",
        default_metric_col="lap_time_1",
        metric_cols=(
            "haron_time_4",
            "lap_time_4",
            "haron_time_3",
            "lap_time_3",
            "haron_time_2",
            "lap_time_2",
            "lap_time_1",
        ),
    ),
    WorkoutTozaiSourceSpec(
        name="staging.stg_n_wood_chip",
        label="ウッド raw staging",
        table_name="staging.stg_n_wood_chip",
        date_col="chokyo_date",
        group_col="tozai_cd",
        default_metric_col="lap_time_1",
        metric_cols=(
            "haron_time_10",
            "haron_time_9",
            "haron_time_8",
            "haron_time_7",
            "haron_time_6",
            "haron_time_5",
            "haron_time_4",
            "haron_time_3",
            "haron_time_2",
            "lap_time_10",
            "lap_time_9",
            "lap_time_8",
            "lap_time_7",
            "lap_time_6",
            "lap_time_5",
            "lap_time_4",
            "lap_time_3",
            "lap_time_2",
            "lap_time_1",
        ),
    ),
    WorkoutTozaiSourceSpec(
        name="mart_wood_current",
        label="m_train representative wood current",
        table_name="mart.m_train_race_horse_past5",
        date_col="held_date",
        group_col="wood_tozai_cd",
        default_metric_col="wood_lap_time_1",
        metric_cols=(
            "wood_haron_time_4",
            "wood_haron_time_6",
            "wood_lap_time_2",
            "wood_lap_time_1",
            "wood_haron_time_4_z_tozai_day",
            "wood_lap_time_1_z_tozai_day",
            "wood_late_sharpness",
        ),
    ),
    WorkoutTozaiSourceSpec(
        name="mart_wood_week1",
        label="m_train representative wood week1",
        table_name="mart.m_train_race_horse_past5",
        date_col="held_date",
        group_col="week1_wood_tozai_cd",
        default_metric_col="week1_wood_lap_time_1",
        metric_cols=(
            "week1_wood_haron_time_4",
            "week1_wood_haron_time_6",
            "week1_wood_lap_time_2",
            "week1_wood_lap_time_1",
            "week1_wood_haron_time_4_z_tozai_day",
            "week1_wood_lap_time_1_z_tozai_day",
            "week1_wood_late_sharpness",
        ),
    ),
    WorkoutTozaiSourceSpec(
        name="mart_hanro_current",
        label="m_train representative hanro current",
        table_name="mart.m_train_race_horse_past5",
        date_col="held_date",
        group_col="hanro_tozai_cd",
        default_metric_col="hanro_lap_time_1",
        metric_cols=(
            "hanro_haron_time_4",
            "hanro_lap_time_2",
            "hanro_lap_time_1",
            "hanro_haron_time_4_z_tozai_day",
            "hanro_lap_time_1_z_tozai_day",
            "hanro_late_sharpness",
        ),
    ),
    WorkoutTozaiSourceSpec(
        name="mart_hanro_week1",
        label="m_train representative hanro week1",
        table_name="mart.m_train_race_horse_past5",
        date_col="held_date",
        group_col="week1_hanro_tozai_cd",
        default_metric_col="week1_hanro_lap_time_1",
        metric_cols=(
            "week1_hanro_haron_time_4",
            "week1_hanro_lap_time_2",
            "week1_hanro_lap_time_1",
            "week1_hanro_haron_time_4_z_tozai_day",
            "week1_hanro_lap_time_1_z_tozai_day",
            "week1_hanro_late_sharpness",
        ),
    ),
)

DEFAULT_WORKOUT_TOZAI_SOURCE_NAMES: tuple[str, ...] = tuple(
    spec.name for spec in DEFAULT_WORKOUT_TOZAI_SOURCE_SPECS
)
_SOURCE_SPEC_MAP = {spec.name: spec for spec in DEFAULT_WORKOUT_TOZAI_SOURCE_SPECS}


def build_workout_tozai_source_catalog(
    source_names: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    resolved_names = list(source_names) if source_names is not None else list(DEFAULT_WORKOUT_TOZAI_SOURCE_NAMES)
    rows: list[dict[str, object]] = []
    for name in resolved_names:
        spec = _SOURCE_SPEC_MAP.get(name)
        if spec is None:
            continue
        rows.append(
            {
                **asdict(spec),
                "metric_cols": ", ".join(spec.metric_cols),
                "n_metric_cols": len(spec.metric_cols),
            }
        )
    return pd.DataFrame(rows)


def resolve_workout_tozai_source_spec(name: str) -> WorkoutTozaiSourceSpec:
    spec = _SOURCE_SPEC_MAP.get(name)
    if spec is None:
        raise KeyError(f"source spec not found: {name}")
    return spec


def build_metric_catalog(source_name: str) -> pd.DataFrame:
    spec = resolve_workout_tozai_source_spec(source_name)
    return pd.DataFrame(
        {
            "source_name": [spec.name] * len(spec.metric_cols),
            "source_label": [spec.label] * len(spec.metric_cols),
            "metric_col": list(spec.metric_cols),
            "is_default": [metric == spec.default_metric_col for metric in spec.metric_cols],
        }
    )


def prepare_tozai_distribution_frame(
    df: pd.DataFrame,
    *,
    metric_col: str,
    group_col: str = "tozai_cd",
    date_col: str = "chokyo_date",
) -> pd.DataFrame:
    local = pd.DataFrame(index=df.index)
    local["metric_value"] = _coerce_numeric(df[metric_col])
    local["tozai_cd"] = _coerce_numeric(df[group_col])
    if date_col in df.columns:
        local["chokyo_date"] = pd.to_datetime(df[date_col], errors="coerce")

    local = local.dropna(subset=["metric_value", "tozai_cd"]).copy()
    if local.empty:
        return pd.DataFrame(columns=["metric_value", "tozai_cd", "tozai_label", "chokyo_date", "year"])

    local["tozai_cd"] = local["tozai_cd"].astype("int64")
    local["tozai_label"] = local["tozai_cd"].map(lambda value: f"tozai_cd={int(value)}")
    if "chokyo_date" in local.columns:
        local["year"] = local["chokyo_date"].dt.year.astype("Int64")
    return local.reset_index(drop=True)


def build_tozai_distribution_summary(
    df: pd.DataFrame,
    *,
    metric_col: str,
    group_col: str = "tozai_cd",
    date_col: str = "chokyo_date",
) -> pd.DataFrame:
    base = pd.DataFrame(index=df.index)
    base["tozai_cd"] = _coerce_numeric(df[group_col])
    base["metric_value"] = _coerce_numeric(df[metric_col])
    if date_col in df.columns:
        base["chokyo_date"] = pd.to_datetime(df[date_col], errors="coerce")

    base = base.dropna(subset=["tozai_cd"]).copy()
    if base.empty:
        return pd.DataFrame()

    base["tozai_cd"] = base["tozai_cd"].astype("int64")
    base["tozai_label"] = base["tozai_cd"].map(lambda value: f"tozai_cd={int(value)}")

    total_counts = (
        base.groupby(["tozai_cd", "tozai_label"], dropna=False)
        .size()
        .rename("n_total")
        .reset_index()
    )

    observed = base.dropna(subset=["metric_value"]).copy()
    if observed.empty:
        summary = total_counts.copy()
        summary["n_obs"] = 0
        summary["observed_rate"] = 0.0
        summary["missing_rate"] = 1.0
        return summary

    stats = (
        observed.groupby(["tozai_cd", "tozai_label"], dropna=False)["metric_value"]
        .agg(["size", "mean", "std", "median", "min", "max"])
        .rename(columns={"size": "n_obs"})
        .reset_index()
    )
    quantiles = (
        observed.groupby(["tozai_cd", "tozai_label"], dropna=False)["metric_value"]
        .quantile([0.10, 0.25, 0.75, 0.90])
        .unstack()
        .rename(columns={0.10: "p10", 0.25: "p25", 0.75: "p75", 0.90: "p90"})
        .reset_index()
    )
    summary = total_counts.merge(stats, on=["tozai_cd", "tozai_label"], how="left").merge(
        quantiles,
        on=["tozai_cd", "tozai_label"],
        how="left",
    )
    summary["n_obs"] = summary["n_obs"].fillna(0).astype("int64")
    summary["observed_rate"] = summary["n_obs"] / summary["n_total"]
    summary["missing_rate"] = 1.0 - summary["observed_rate"]
    return summary.sort_values("tozai_cd", ignore_index=True)


def _sample_values(
    values: pd.Series,
    *,
    max_samples: int,
    random_state: int,
) -> np.ndarray:
    clean = _coerce_numeric(values).dropna()
    if clean.shape[0] <= max_samples:
        return clean.to_numpy(dtype="float64", copy=False)
    return (
        clean.sample(n=max_samples, random_state=random_state)
        .to_numpy(dtype="float64", copy=False)
    )


def build_tozai_pairwise_test_summary(
    df: pd.DataFrame,
    *,
    metric_col: str,
    group_col: str = "tozai_cd",
    date_col: str = "chokyo_date",
    max_test_samples: int = 100_000,
    random_state: int = 42,
) -> pd.DataFrame:
    local = prepare_tozai_distribution_frame(df, metric_col=metric_col, group_col=group_col, date_col=date_col)
    if local.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    group_values = {
        int(group): local.loc[local["tozai_cd"] == group, "metric_value"]
        for group in sorted(local["tozai_cd"].unique())
    }
    for group_a, group_b in combinations(sorted(group_values), 2):
        values_a = group_values[group_a]
        values_b = group_values[group_b]
        sample_a = _sample_values(values_a, max_samples=max_test_samples, random_state=random_state + group_a)
        sample_b = _sample_values(values_b, max_samples=max_test_samples, random_state=random_state + group_b)

        if sample_a.size == 0 or sample_b.size == 0:
            continue

        ks_res = ks_2samp(sample_a, sample_b, alternative="two-sided", method="auto")
        mw_res = mannwhitneyu(sample_a, sample_b, alternative="two-sided", method="asymptotic")

        mean_diff = float(values_b.mean() - values_a.mean())
        median_diff = float(values_b.median() - values_a.median())
        pooled_sd = math.sqrt(
            max(
                0.0,
                (
                    ((len(sample_a) - 1) * float(np.var(sample_a, ddof=1)))
                    + ((len(sample_b) - 1) * float(np.var(sample_b, ddof=1)))
                )
                / max(1, len(sample_a) + len(sample_b) - 2),
            )
        )
        cohen_d = mean_diff / pooled_sd if pooled_sd > 0.0 else math.nan

        rows.append(
            {
                "group_a": int(group_a),
                "group_b": int(group_b),
                "group_a_label": f"tozai_cd={int(group_a)}",
                "group_b_label": f"tozai_cd={int(group_b)}",
                "n_obs_group_a": int(values_a.shape[0]),
                "n_obs_group_b": int(values_b.shape[0]),
                "n_test_group_a": int(sample_a.shape[0]),
                "n_test_group_b": int(sample_b.shape[0]),
                "mean_group_a": float(values_a.mean()),
                "mean_group_b": float(values_b.mean()),
                "median_group_a": float(values_a.median()),
                "median_group_b": float(values_b.median()),
                "mean_diff_b_minus_a": mean_diff,
                "median_diff_b_minus_a": median_diff,
                "cohen_d_b_minus_a": float(cohen_d),
                "ks_statistic": float(ks_res.statistic),
                "ks_pvalue": float(ks_res.pvalue),
                "mannwhitney_u": float(mw_res.statistic),
                "mannwhitney_pvalue": float(mw_res.pvalue),
                "test_note": "pairwise tests use sampled rows when group size exceeds max_test_samples",
            }
        )

    return pd.DataFrame(rows)


def build_tozai_yearly_summary(
    df: pd.DataFrame,
    *,
    metric_col: str,
    group_col: str = "tozai_cd",
    date_col: str = "chokyo_date",
) -> pd.DataFrame:
    local = prepare_tozai_distribution_frame(df, metric_col=metric_col, group_col=group_col, date_col=date_col)
    if local.empty or "year" not in local.columns:
        return pd.DataFrame()

    local = local.dropna(subset=["year"]).copy()
    if local.empty:
        return pd.DataFrame()

    yearly = (
        local.groupby(["year", "tozai_cd", "tozai_label"], dropna=False)["metric_value"]
        .agg(["size", "mean", "median"])
        .rename(columns={"size": "n_obs"})
        .reset_index()
    )
    quantiles = (
        local.groupby(["year", "tozai_cd", "tozai_label"], dropna=False)["metric_value"]
        .quantile([0.25, 0.75])
        .unstack()
        .rename(columns={0.25: "p25", 0.75: "p75"})
        .reset_index()
    )
    return yearly.merge(quantiles, on=["year", "tozai_cd", "tozai_label"], how="left").sort_values(
        ["year", "tozai_cd"],
        ignore_index=True,
    )
