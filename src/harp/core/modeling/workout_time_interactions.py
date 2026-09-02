from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd

from .workout_time_relationships import (
    _coerce_numeric,
    _fit_logistic_summary,
    _rank_quantile_bucket,
    _standardize,
    _wilson_interval,
)


@dataclass(frozen=True)
class WorkoutInteractionSpec:
    name: str
    label: str
    family: str
    timing: str
    last1f_col: str
    total4f_col: str


DEFAULT_WORKOUT_INTERACTION_SPECS: tuple[WorkoutInteractionSpec, ...] = (
    WorkoutInteractionSpec(
        name="wood_current",
        label="直前ウッド 4F × 1F",
        family="wood",
        timing="current",
        last1f_col="wood_lap_time_1",
        total4f_col="wood_haron_time_4",
    ),
    WorkoutInteractionSpec(
        name="hanro_current",
        label="直前坂路 4F × 1F",
        family="hanro",
        timing="current",
        last1f_col="hanro_lap_time_1",
        total4f_col="hanro_haron_time_4",
    ),
    WorkoutInteractionSpec(
        name="wood_week1",
        label="1週前ウッド 4F × 1F",
        family="wood",
        timing="week1",
        last1f_col="week1_wood_lap_time_1",
        total4f_col="week1_wood_haron_time_4",
    ),
    WorkoutInteractionSpec(
        name="hanro_week1",
        label="1週前坂路 4F × 1F",
        family="hanro",
        timing="week1",
        last1f_col="week1_hanro_lap_time_1",
        total4f_col="week1_hanro_haron_time_4",
    ),
)

DEFAULT_WORKOUT_INTERACTION_NAMES: tuple[str, ...] = tuple(
    spec.name for spec in DEFAULT_WORKOUT_INTERACTION_SPECS
)
_INTERACTION_SPEC_MAP = {spec.name: spec for spec in DEFAULT_WORKOUT_INTERACTION_SPECS}


def build_interaction_catalog(
    interaction_names: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    resolved_names = list(interaction_names) if interaction_names is not None else list(DEFAULT_WORKOUT_INTERACTION_NAMES)
    rows: list[dict[str, object]] = []
    for name in resolved_names:
        spec = _INTERACTION_SPEC_MAP.get(name)
        if spec is None:
            continue
        rows.append(asdict(spec))
    return pd.DataFrame(rows)


def available_interaction_names(
    df: pd.DataFrame,
    interaction_names: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    requested = list(interaction_names) if interaction_names is not None else list(DEFAULT_WORKOUT_INTERACTION_NAMES)
    available: list[str] = []
    for name in requested:
        spec = _INTERACTION_SPEC_MAP.get(name)
        if spec is None:
            continue
        if spec.last1f_col in df.columns and spec.total4f_col in df.columns:
            available.append(name)
    return available


def resolve_interaction_spec(name: str) -> WorkoutInteractionSpec:
    spec = _INTERACTION_SPEC_MAP.get(name)
    if spec is None:
        raise KeyError(f"interaction spec not found: {name}")
    return spec


def _prepare_pair_frame(
    df: pd.DataFrame,
    *,
    spec: WorkoutInteractionSpec,
    target_col: str,
    result_order_col: str = "result_order",
    control_cols: list[str] | tuple[str, ...] = ("surface", "distance_m", "race_level", "held_year"),
) -> pd.DataFrame:
    local = pd.DataFrame(index=df.index)
    local["last1f"] = _coerce_numeric(df[spec.last1f_col])
    local["total4f"] = _coerce_numeric(df[spec.total4f_col])
    local["target"] = _coerce_numeric(df[target_col])
    if result_order_col in df.columns:
        local["result_order"] = _coerce_numeric(df[result_order_col])
    for control_col in control_cols:
        if control_col in df.columns:
            local[control_col] = _coerce_numeric(df[control_col])

    local = local.dropna(subset=["last1f", "total4f", "target"])
    if local.empty:
        return pd.DataFrame()

    local["first3f_avg"] = (local["total4f"] - local["last1f"]) / 3.0
    local["late_sharpness"] = local["first3f_avg"] - local["last1f"]
    local["last1f_fast"] = -_standardize(local["last1f"])
    local["total4f_fast"] = -_standardize(local["total4f"])
    local["late_sharpness_z"] = _standardize(local["late_sharpness"])
    local["interaction_fast_x_total"] = local["last1f_fast"] * local["total4f_fast"]
    return local


def build_interaction_effect_summary(
    df: pd.DataFrame,
    interaction_names: list[str] | tuple[str, ...] | None = None,
    *,
    target_col: str = "is_place",
    result_order_col: str = "result_order",
    control_cols: list[str] | tuple[str, ...] = ("surface", "distance_m", "race_level", "held_year"),
) -> pd.DataFrame:
    names = available_interaction_names(df, interaction_names)
    if not names:
        return pd.DataFrame()

    catalog = build_interaction_catalog(names).set_index("name", drop=False)
    rows: list[dict[str, object]] = []
    for name in names:
        spec = resolve_interaction_spec(name)
        local = _prepare_pair_frame(
            df,
            spec=spec,
            target_col=target_col,
            result_order_col=result_order_col,
            control_cols=control_cols,
        )
        if local.empty:
            continue

        interaction_cols = ["last1f_fast", "total4f_fast", "interaction_fast_x_total"]
        interaction_summary = _fit_logistic_summary(
            local[interaction_cols],
            local["target"],
            focus_col="interaction_fast_x_total",
        )

        late_cols = ["late_sharpness_z", *[col for col in control_cols if col in local.columns]]
        late_summary = _fit_logistic_summary(
            local[late_cols],
            local["target"],
            focus_col="late_sharpness_z",
        )

        rows.append(
            {
                **catalog.loc[name].to_dict(),
                "n_obs": int(local.shape[0]),
                "target_rate": float(local["target"].mean()),
                "mean_last1f": float(local["last1f"].mean()),
                "mean_total4f": float(local["total4f"].mean()),
                "mean_late_sharpness": float(local["late_sharpness"].mean()),
                "coef_interaction_fast_x_total": interaction_summary["coef"],
                "auc_interaction_model": interaction_summary["auc"],
                "brier_interaction_model": interaction_summary["brier"],
                "coef_late_sharpness_per_1sd": late_summary["coef"],
                "auc_late_sharpness_model": late_summary["auc"],
                "brier_late_sharpness_model": late_summary["brier"],
            }
        )

    return pd.DataFrame(rows)


def build_last1f_4f_heatmap_summary(
    df: pd.DataFrame,
    *,
    spec_name: str,
    target_col: str = "is_place",
    n_bins: int = 6,
) -> pd.DataFrame:
    spec = resolve_interaction_spec(spec_name)
    local = _prepare_pair_frame(df, spec=spec, target_col=target_col)
    if local.empty:
        return pd.DataFrame()

    local["last1f_bin"] = _rank_quantile_bucket(local["last1f"], n_bins=n_bins, ascending=True)
    local["total4f_bin"] = _rank_quantile_bucket(local["total4f"], n_bins=n_bins, ascending=True)
    grouped = (
        local.groupby(["total4f_bin", "last1f_bin"], dropna=True)
        .agg(
            n_obs=("target", "size"),
            hit_count=("target", "sum"),
            target_rate=("target", "mean"),
            mean_last1f=("last1f", "mean"),
            mean_total4f=("total4f", "mean"),
            mean_late_sharpness=("late_sharpness", "mean"),
        )
        .reset_index()
        .sort_values(["total4f_bin", "last1f_bin"], ignore_index=True)
    )

    ci_low: list[float] = []
    ci_high: list[float] = []
    for _, row in grouped.iterrows():
        low, high = _wilson_interval(int(row["hit_count"]), int(row["n_obs"]))
        ci_low.append(low)
        ci_high.append(high)

    grouped["target_rate_ci_low"] = ci_low
    grouped["target_rate_ci_high"] = ci_high
    grouped["total4f_band"] = grouped["total4f_bin"].map(lambda x: f"{int(x):02d}")
    grouped["last1f_band"] = grouped["last1f_bin"].map(lambda x: f"{int(x):02d}")
    return grouped


def build_heatmap_matrix(
    heatmap_summary_df: pd.DataFrame,
    *,
    value_col: str = "target_rate",
) -> pd.DataFrame:
    if heatmap_summary_df.empty:
        return pd.DataFrame()
    matrix = heatmap_summary_df.pivot(
        index="total4f_bin",
        columns="last1f_bin",
        values=value_col,
    ).sort_index(axis=0).sort_index(axis=1)
    return matrix


def build_late_sharpness_decile_summary(
    df: pd.DataFrame,
    *,
    spec_name: str,
    target_col: str = "is_place",
    n_bins: int = 10,
) -> pd.DataFrame:
    spec = resolve_interaction_spec(spec_name)
    local = _prepare_pair_frame(df, spec=spec, target_col=target_col)
    if local.empty:
        return pd.DataFrame()

    local["late_sharpness_bin"] = _rank_quantile_bucket(local["late_sharpness"], n_bins=n_bins, ascending=False)
    grouped = (
        local.groupby("late_sharpness_bin", dropna=True)
        .agg(
            n_obs=("target", "size"),
            hit_count=("target", "sum"),
            target_rate=("target", "mean"),
            mean_late_sharpness=("late_sharpness", "mean"),
            mean_last1f=("last1f", "mean"),
            mean_total4f=("total4f", "mean"),
        )
        .reset_index()
        .sort_values("late_sharpness_bin", ignore_index=True)
    )
    ci_low: list[float] = []
    ci_high: list[float] = []
    for _, row in grouped.iterrows():
        low, high = _wilson_interval(int(row["hit_count"]), int(row["n_obs"]))
        ci_low.append(low)
        ci_high.append(high)
    grouped["target_rate_ci_low"] = ci_low
    grouped["target_rate_ci_high"] = ci_high
    grouped["late_sharpness_band"] = grouped["late_sharpness_bin"].map(lambda x: f"{int(x):02d}")
    return grouped


def build_within_total4f_band_sharpness_summary(
    df: pd.DataFrame,
    *,
    spec_name: str,
    target_col: str = "is_place",
    n_total4f_bins: int = 5,
    n_sharpness_bins: int = 4,
) -> pd.DataFrame:
    spec = resolve_interaction_spec(spec_name)
    local = _prepare_pair_frame(df, spec=spec, target_col=target_col)
    if local.empty:
        return pd.DataFrame()

    local["total4f_bin"] = _rank_quantile_bucket(local["total4f"], n_bins=n_total4f_bins, ascending=True)
    summary_rows: list[dict[str, object]] = []

    for total4f_bin, part in local.groupby("total4f_bin", dropna=True):
        sharpness_bins = _rank_quantile_bucket(part["late_sharpness"], n_bins=n_sharpness_bins, ascending=False)
        scoped = part.copy()
        scoped["late_sharpness_bin"] = sharpness_bins
        grouped = (
            scoped.groupby("late_sharpness_bin", dropna=True)
            .agg(
                n_obs=("target", "size"),
                target_rate=("target", "mean"),
                mean_late_sharpness=("late_sharpness", "mean"),
            )
            .reset_index()
            .sort_values("late_sharpness_bin", ignore_index=True)
        )
        if grouped.empty:
            continue

        top = grouped.iloc[0]
        bottom = grouped.iloc[-1]
        summary_rows.append(
            {
                "total4f_bin": int(total4f_bin),
                "n_fastest_sharpness": int(top["n_obs"]),
                "target_rate_fastest_sharpness": float(top["target_rate"]),
                "mean_late_sharpness_fastest": float(top["mean_late_sharpness"]),
                "n_slowest_sharpness": int(bottom["n_obs"]),
                "target_rate_slowest_sharpness": float(bottom["target_rate"]),
                "mean_late_sharpness_slowest": float(bottom["mean_late_sharpness"]),
                "delta_target_rate_fastest_minus_slowest": float(top["target_rate"] - bottom["target_rate"]),
            }
        )

    out = pd.DataFrame(summary_rows)
    if out.empty:
        return out
    out["total4f_band"] = out["total4f_bin"].map(lambda x: f"{int(x):02d}")
    return out.sort_values("total4f_bin", ignore_index=True)
